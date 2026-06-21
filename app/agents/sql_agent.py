"""SQL agent — exposes the ``query_database`` capability tool.

The SQL agent is the only component permitted to touch the database (AGENTS.md
§5, §9). It wraps an inner, autonomous ``create_agent`` that generates SQL,
validates it read-only, executes it via :class:`QueryService`, and self-corrects
through its own reasoning loop. The outer ``query_database`` tool — returned by
:meth:`SqlAgent.get_tools` for the supervisor graph — invokes that inner agent
and maps the outcome onto typed ``WorkflowState`` fields via a ``Command``.

Contracts consumed/produced: :class:`SQLGenerationOutput` (inner structured
response) and :class:`QueryResult` (execution result written to state).
"""

from typing import Annotated, Optional

from langchain.agents import AgentState, create_agent
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, InjectedToolCallId, tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from app.config.env_config import settings
from app.config.log_config import get_logger
from app.orchestration.state import WorkflowState
from app.prompts.sql_prompt import SQL_SYSTEM_PROMPT
from app.schemas.sql_result import QueryResult, SQLGenerationOutput
from app.services.sql_service import QueryService
from app.utils.validators import validate_select_only

logger = get_logger(__name__)

# Standard user-facing error messages (FRS §10 / AGENTS.md §9).
_ERR_UNIDENTIFIED = "Unable to identify requested entities."
_ERR_VALIDATION = "Generated query could not be validated."
_ERR_DATABASE = "Unable to retrieve data at this time."
_ERR_EMPTY = "No data found for the requested query."


class SqlAgentState(AgentState):
    """State for the inner SQL agent (extends ``AgentState``).

    ``AgentState`` provides ``messages`` and ``structured_response``; these fields
    let the inner ``validate_and_execute`` tool hand results back to the outer tool
    via the agent's return value, avoiding any shared mutable state across the
    concurrently-reused agent instance.

    Attributes:
        query_result: Execution result, set on a successful run.
        error_type: ``"validation"`` or ``"database"`` when execution failed.
    """

    query_result: Optional[QueryResult]
    error_type: Optional[str]


class SqlAgent:
    """Provides the ``query_database`` tool backed by an autonomous SQL agent."""

    def __init__(
        self,
        llm: ChatGoogleGenerativeAI,
        query_service: QueryService,
        retry_limit: int | None = None,
    ) -> None:
        """Build the inner autonomous agent and its execution tool.

        Args:
            llm: The chat model the inner agent uses to generate/correct SQL.
            query_service: Executes validated SQL (the only DB pathway).
            retry_limit: Max self-correction attempts; bounds the inner agent's
                tool-calling loop via ``recursion_limit``. Defaults to
                ``settings.sql_retry_limit`` (the ``SQL_RETRY_LIMIT`` env var).
        """
        self._query_service = query_service
        self._retry_limit = (
            retry_limit if retry_limit is not None else settings.sql_retry_limit
        )
        logger.info("SqlAgent initializing (retry_limit=%d)", self._retry_limit)
        self._agent = create_agent(
            model=llm,
            tools=[self._build_validate_and_execute()],
            system_prompt=SQL_SYSTEM_PROMPT,
            response_format=SQLGenerationOutput,
            state_schema=SqlAgentState,
        )

    def _build_validate_and_execute(self) -> BaseTool:
        """Return the inner ``validate_and_execute`` tool (closure over the service)."""
        query_service = self._query_service

        @tool
        def validate_and_execute(
            sql: str,
            tool_call_id: Annotated[str, InjectedToolCallId],
        ) -> Command:
            """Validate that SQL is read-only and execute it.

            Returns a brief result/error summary the agent uses to self-correct,
            and writes the outcome into the inner agent state.

            Args:
                sql: The SQL the agent wants to run.
                tool_call_id: Injected id for the response ``ToolMessage``.

            Returns:
                A ``Command`` updating ``query_result``/``error_type`` plus a
                ``ToolMessage`` summary.
            """
            if not validate_select_only(sql):
                logger.warning(
                    "validate_and_execute: read-only check failed for SQL: %s",
                    sql[:200],
                )
                return Command(
                    update={
                        "error_type": "validation",
                        "messages": [
                            ToolMessage(
                                content=(
                                    "Validation failed: query contains write/DDL. "
                                    "Generate a SELECT-only query."
                                ),
                                tool_call_id=tool_call_id,
                            )
                        ],
                    }
                )
            logger.debug("SQL passed read-only validation: %s", sql[:200])
            try:
                result = query_service.run_query(sql)
            except Exception as exc:  # noqa: BLE001 — classified, fed back to the agent
                logger.warning("SQL execution failed: %s", exc)
                return Command(
                    update={
                        "error_type": "database",
                        "messages": [
                            ToolMessage(
                                content=(
                                    f"Execution error: {exc!s}. Please correct the query."
                                ),
                                tool_call_id=tool_call_id,
                            )
                        ],
                    }
                )
            logger.info(
                "validate_and_execute: query returned %d row(s), columns=%s",
                result.row_count,
                result.columns,
            )
            summary = (
                f"retrieved {result.row_count} rows. "
                f"Columns: {', '.join(result.columns)}"
                if result.row_count
                else "Query succeeded but returned 0 rows."
            )
            return Command(
                update={
                    "query_result": result,
                    "error_type": None,
                    "messages": [
                        ToolMessage(content=summary, tool_call_id=tool_call_id)
                    ],
                }
            )

        return validate_and_execute

    def get_tools(self) -> list[BaseTool]:
        """Return the supervisor-facing tools provided by this agent.

        Returns:
            ``[query_database]`` — the capability tool the supervisor sequences.
        """
        agent = self._agent
        retry_limit = self._retry_limit

        @tool
        def query_database(
            question: str,
            tool_call_id: Annotated[str, InjectedToolCallId],
            _state: Annotated[WorkflowState, InjectedState],
        ) -> Command:
            """Answer a question by generating, validating, and executing SQL.

            Runs the inner autonomous SQL agent, then maps its outcome onto typed
            ``WorkflowState`` fields. On success ``query_result`` is set and any
            stale ``error_message`` is cleared; every failure clears
            ``query_result`` and sets the standard user-facing ``error_message``.

            Args:
                question: The user's natural-language question.
                tool_call_id: Injected id for the response ``ToolMessage``.
                _state: Injected workflow state (unused in this issue).

            Returns:
                A ``Command`` updating the workflow state.
            """
            logger.info("query_database invoked: question=%r", question[:120])
            inner = agent.invoke(
                {"messages": [{"role": "user", "content": question}]},
                config={"recursion_limit": retry_limit * 2 + 1},
            )
            output: SQLGenerationOutput = inner["structured_response"]
            logger.debug(
                "Inner SQL agent finished: identifiable=%s sql=%s",
                output.is_identifiable,
                (output.sql or "")[:200],
            )

            if not output.is_identifiable:
                logger.warning(
                    "query_database: entities not identifiable in schema — question=%r",
                    question[:120],
                )
                return Command(
                    update={
                        "error_message": _ERR_UNIDENTIFIED,
                        "query_result": None,
                        "messages": [
                            ToolMessage(
                                content=_ERR_UNIDENTIFIED, tool_call_id=tool_call_id
                            )
                        ],
                    }
                )

            base_update = {
                "generated_sql": output.sql,
                "sql_explanation": output.explanation,
            }
            logger.info("Generated SQL: %s", (output.sql or "")[:300])
            query_result: QueryResult | None = inner.get("query_result")
            error_type: str | None = inner.get("error_type")

            if query_result is None:
                message = _ERR_DATABASE if error_type == "database" else _ERR_VALIDATION
                logger.warning(
                    "query_database: no result after inner agent (error_type=%s)",
                    error_type,
                )
                return Command(
                    update={
                        **base_update,
                        "query_result": None,
                        "error_message": message,
                        "messages": [
                            ToolMessage(content=message, tool_call_id=tool_call_id)
                        ],
                    }
                )

            if query_result.row_count == 0:
                logger.warning("query_database: query succeeded but returned 0 rows")
                return Command(
                    update={
                        **base_update,
                        "query_result": None,
                        "error_message": _ERR_EMPTY,
                        "messages": [
                            ToolMessage(content=_ERR_EMPTY, tool_call_id=tool_call_id)
                        ],
                    }
                )

            logger.info(
                "query_database succeeded: %d row(s), columns=%s",
                query_result.row_count,
                query_result.columns,
            )
            summary = (
                f"retrieved {query_result.row_count} rows. "
                f"Columns: {', '.join(query_result.columns)}"
            )
            return Command(
                update={
                    **base_update,
                    "query_result": query_result,
                    "error_message": None,
                    "messages": [
                        ToolMessage(content=summary, tool_call_id=tool_call_id)
                    ],
                }
            )

        return [query_database]
