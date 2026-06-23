"""SQL tools provided to SqlAgent.

``SqlTools`` builds the four ``@tool``-decorated closures the ``SqlAgent``'s
``create_agent()`` instance uses as internal tools. All four are constructed in
``__init__``, capture injected deps (``llm``, ``api_base_url``), and are stored
as instance attributes so ``SqlAgent`` can pass them by name to ``create_agent``.

Contracts consumed/produced: :class:`~app.schemas.sql_result.SQLGenerationOutput`
(returned by ``generate_sql``) and :class:`~app.schemas.sql_result.QueryResult`
(rows stored as ``list[dict]``, written to ``WorkflowState.query_result`` via ``Command``).
"""

from typing import Annotated

import httpx
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Command

from app.config.log_config import config as log_config
from app.prompts.sql_prompt import SQL_SYSTEM_PROMPT
from app.schemas.sql_result import QueryResult, SQLGenerationOutput
from app.utils.validators import validate_select_only

logger = log_config.get_logger(__name__)

_ERR_UNIDENTIFIED = "Unable to identify requested entities."
_ERR_VALIDATION = "Generated query could not be validated."
_ERR_DATABASE = "Unable to retrieve data at this time."
_ERR_EMPTY = "No data found for the requested query."


class SqlTools:
    """Builds the four internal tools for ``SqlAgent``.

    All tools are ``@tool``-decorated closures defined in ``__init__`` that
    capture injected dependencies (``llm``, ``api_base_url``) and are exposed as
    instance attributes.  ``SqlAgent`` passes them directly to ``create_agent``::

        tools=[
            sql_tools.generate_sql,
            sql_tools.validate_sql,
            sql_tools.execute_sql,
            sql_tools.handle_unidentifiable,
        ]

    Args:
        llm: Chat model for the ``generate_sql`` nested structured-output call.
        api_base_url: Base URL for ``POST /api/query`` calls in ``execute_sql``.
    """

    def __init__(self, llm, api_base_url: str) -> None:
        """Build four ``@tool`` closures and expose as instance attributes."""

        @tool
        def generate_sql(question: str) -> SQLGenerationOutput:
            """Generate a SQLite SELECT query for the question.

            Makes a nested ``llm.with_structured_output(SQLGenerationOutput)``
            call using ``SQL_SYSTEM_PROMPT`` as the system message. Returns a
            :class:`SQLGenerationOutput` with ``is_identifiable=False`` if the
            question references entities not present in the schema.

            Args:
                question: The user's natural-language question.

            Returns:
                :class:`SQLGenerationOutput` with ``sql``, ``explanation``,
                ``is_identifiable``.
            """
            chain = llm.with_structured_output(SQLGenerationOutput)
            result: SQLGenerationOutput = chain.invoke(
                [
                    SystemMessage(content=SQL_SYSTEM_PROMPT),
                    HumanMessage(content=question),
                ]
            )
            logger.debug(
                "generate_sql: identifiable=%s sql=%.200s",
                result.is_identifiable,
                result.sql or "",
            )
            return result

        @tool
        def validate_sql(sql: str) -> dict:
            """Validate that ``sql`` is a ``SELECT``-only statement.

            Calls ``app/utils/validators.validate_select_only``. Returns
            ``{"valid": True}`` on success or ``{"valid": False, "reason": "..."}``.
            Feedback only — does not write to ``WorkflowState``. The caller LLM
            retries ``generate_sql`` on failure.

            Args:
                sql: The generated SQL string to validate.

            Returns:
                dict with ``"valid"`` bool and optional ``"reason"`` string.
            """
            if validate_select_only(sql):
                logger.debug("validate_sql: passed for sql=%.100s", sql)
                return {"valid": True}
            logger.warning("validate_sql: rejected non-SELECT sql=%.200s", sql)
            return {
                "valid": False,
                "reason": (
                    "Only SELECT statements are permitted. "
                    "Rewrite the query without INSERT, UPDATE, DELETE, DROP, "
                    "ALTER, or TRUNCATE."
                ),
            }

        @tool
        def execute_sql(
            sql: str,
            explanation: str,
            tool_call_id: Annotated[str, InjectedToolCallId],
        ) -> Command:
            """Defense-in-depth validate then ``POST /api/query``.

            Applies a secondary ``validate_select_only`` check before calling
            the API (defense-in-depth per AGENTS.md §9). On success writes
            ``generated_sql``, ``sql_explanation``, ``query_result``, and
            ``error_message=None`` to ``WorkflowState``. On any failure writes
            ``error_message`` and clears ``query_result``.

            Args:
                sql: The validated SELECT query to execute.
                explanation: Plain-English description of the query from
                    ``generate_sql``.
                tool_call_id: Injected id for the response ``ToolMessage``.

            Returns:
                :class:`~langgraph.types.Command` updating ``WorkflowState``
                fields.
            """
            if not validate_select_only(sql):
                logger.warning(
                    "execute_sql: defense-in-depth check blocked sql=%.200s", sql
                )
                return Command(
                    update={
                        "error_message": _ERR_VALIDATION,
                        "query_result": None,
                        "messages": [
                            ToolMessage(
                                content=_ERR_VALIDATION,
                                tool_call_id=tool_call_id,
                            )
                        ],
                    }
                )
            try:
                with httpx.Client() as client:
                    response = client.post(
                        f"{api_base_url}/api/query",
                        json={"sql": sql},
                        timeout=30.0,
                    )
                    response.raise_for_status()
                    data = response.json()
                result = QueryResult(
                    rows=data["rows"],
                    columns=data["columns"],
                    row_count=data["row_count"],
                )
            except Exception as exc:  # noqa: BLE001 — classified, fed back to agent
                logger.warning("execute_sql: HTTP/DB error: %s", exc)
                return Command(
                    update={
                        "error_message": _ERR_DATABASE,
                        "query_result": None,
                        "messages": [
                            ToolMessage(
                                content=(
                                    f"Execution error: {exc!s}. "
                                    "Correct the query and retry."
                                ),
                                tool_call_id=tool_call_id,
                            )
                        ],
                    }
                )
            if result.row_count == 0:
                logger.warning("execute_sql: query returned 0 rows")
                return Command(
                    update={
                        "error_message": _ERR_EMPTY,
                        "query_result": None,
                        "generated_sql": sql,
                        "sql_explanation": explanation,
                        "messages": [
                            ToolMessage(
                                content=_ERR_EMPTY,
                                tool_call_id=tool_call_id,
                            )
                        ],
                    }
                )
            summary = (
                f"retrieved {result.row_count} rows. "
                f"Columns: {', '.join(result.columns)}"
            )
            logger.info("execute_sql: %s", summary)
            return Command(
                update={
                    "generated_sql": sql,
                    "sql_explanation": explanation,
                    "query_result": result,
                    "error_message": None,
                    "messages": [
                        ToolMessage(content=summary, tool_call_id=tool_call_id)
                    ],
                }
            )

        @tool
        def handle_unidentifiable(
            tool_call_id: Annotated[str, InjectedToolCallId],
        ) -> Command:
            """Terminal handler when ``generate_sql`` returns ``is_identifiable=False``.

            Writes ``error_message=_ERR_UNIDENTIFIED`` to ``WorkflowState`` and
            clears ``query_result`` and ``generated_sql``. ``validate_sql`` and
            ``execute_sql`` MUST NOT be called after this tool.

            Args:
                tool_call_id: Injected id for the response ``ToolMessage``.

            Returns:
                :class:`~langgraph.types.Command` updating ``WorkflowState``
                with the unidentifiable error.
            """
            logger.warning("handle_unidentifiable: question entities not in schema")
            return Command(
                update={
                    "error_message": _ERR_UNIDENTIFIED,
                    "query_result": None,
                    "generated_sql": None,
                    "messages": [
                        ToolMessage(
                            content=_ERR_UNIDENTIFIED,
                            tool_call_id=tool_call_id,
                        )
                    ],
                }
            )

        self.generate_sql = generate_sql
        self.validate_sql = validate_sql
        self.execute_sql = execute_sql
        self.handle_unidentifiable = handle_unidentifiable
