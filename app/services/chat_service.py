"""Chat Service — API-to-workflow bridge.

``ChatService`` is the single component authorised to invoke the compiled
``create_agent`` graph (SDS §9.3). Routes delegate to it; domain services
stay independent of LangGraph. It maintains per-session conversation history
in-memory (FR-11 / SDS §15): only successfully answered turns are appended;
errored ones are not. History is never persisted to the database.
"""

import asyncio

from langchain_core.messages import HumanMessage
from langgraph.graph.state import CompiledStateGraph

from app.config.log_config import config as log_config
from app.schemas.conversation import ConversationTurn
from app.schemas.requests import AnalyticsRequest
from app.schemas.responses import AnalyticsResponse
from app.schemas.sql_result import QueryResult

logger = log_config.get_logger(__name__)

# Standard FRS §10 message used when an unhandled exception escapes the graph.
_ERR_DATABASE = "Unable to retrieve data at this time."

# Allowlist of every valid FRS §10 error string (spec: error-response-safety).
# Any non-None error_message from the graph that is not in this set is replaced
# with _ERR_DATABASE so raw internal strings never leak to callers.
_ALLOWED_ERRORS: frozenset[str] = frozenset(
    {
        "Unable to identify requested entities.",
        "Generated query could not be validated.",
        "No data found for the requested query.",
        "Unable to retrieve data at this time.",
    }
)


class ChatService:
    """Bridges the FastAPI layer and the LangGraph analytics workflow.

    Accepts a compiled ``create_agent`` graph via constructor injection and
    exposes a single ``ask()`` coroutine. All graph invocations are wrapped in
    a try/except so that unhandled exceptions never propagate to the route —
    callers always receive a well-formed ``AnalyticsResponse`` with HTTP 200.

    ``graph.invoke()`` is a blocking call; it is offloaded to a thread via
    ``asyncio.to_thread`` so the event loop stays responsive. All mutations of
    ``_history`` happen after the ``await`` returns, in the single-threaded
    event loop, so no lock is needed.

    Attributes:
        _graph: The compiled LangGraph supervisor graph (shared singleton).
        _history: In-memory session store mapping ``session_uuid`` to an
            ordered list of successfully completed ``ConversationTurn`` objects.
    """

    def __init__(self, graph: CompiledStateGraph) -> None:
        """Store the compiled graph and initialise the session history store.

        Args:
            graph: The compiled ``create_agent`` supervisor, built once at
                application startup by ``AnalyticsGraph.build()``.
        """
        self._graph = graph
        self._history: dict[str, list[ConversationTurn]] = {}

    async def ask(self, request: AnalyticsRequest) -> AnalyticsResponse:
        """Run the analytics workflow for a submitted question.

        Offloads the blocking ``graph.invoke()`` call to a thread pool via
        ``asyncio.to_thread``, then maps final workflow state onto
        ``AnalyticsResponse`` in the event loop. Before invoking the graph,
        injects the current session's prior ``ConversationTurn`` objects into
        ``WorkflowState.conversation_history`` so the agents have multi-turn
        context. If ``query_result`` is set in state, reads ``QueryResult.rows``
        (already ``list[dict]``) directly into the response. Appends a
        ``ConversationTurn`` to session history if and only if the workflow
        completes without an ``error_message``. Any unhandled exception is caught
        and mapped to the standard FRS §10 database-error message; no stack trace
        is exposed.

        Args:
            request: The validated inbound request containing ``question``
                and ``session_uuid``.

        Returns:
            An ``AnalyticsResponse`` with HTTP 200 in all cases.
        """
        logger.info(
            "ask() invoked: session=%s question=%r",
            request.session_uuid,
            request.question[:120],
        )
        prior_turns = list(self._history.get(request.session_uuid, []))
        try:
            logger.debug(
                "Invoking analytics graph for session=%s (prior_turns=%d)",
                request.session_uuid,
                len(prior_turns),
            )
            result = await asyncio.to_thread(
                self._graph.invoke,
                {
                    "question": request.question,
                    "messages": [HumanMessage(content=request.question)],
                    "conversation_history": prior_turns,
                },
            )
            error_message: str | None = result.get("error_message")
            if error_message is not None and error_message not in _ALLOWED_ERRORS:
                logger.warning(
                    "Non-standard error_message from graph (session=%s): %s",
                    request.session_uuid,
                    error_message,
                )
                error_message = _ERR_DATABASE
            query_result_obj: QueryResult | None = result.get("query_result")
            serialized_rows: list[dict] | None = None
            columns: list[str] | None = None
            row_count: int | None = None
            if query_result_obj is not None:
                serialized_rows = query_result_obj.rows
                columns = query_result_obj.columns
                row_count = query_result_obj.row_count
            chart_config_obj = result.get("chart_config")
            chart_config = chart_config_obj.model_dump() if chart_config_obj else None
            # History mutations run in the event loop (after the await) —
            # single-threaded, no lock required.
            if not error_message:
                turn = ConversationTurn(
                    question=request.question,
                    generated_sql=result.get("generated_sql"),
                    sql_explanation=result.get("sql_explanation"),
                    query_result=query_result_obj,
                    chart_config=chart_config_obj,
                    insights=result.get("insights"),
                    followup_questions=result.get("followup_questions"),
                )
                self._history.setdefault(request.session_uuid, []).append(turn)
            logger.info(
                "Workflow complete for session=%s error=%s",
                request.session_uuid,
                error_message,
            )
            return AnalyticsResponse(
                question=request.question,
                generated_sql=result.get("generated_sql"),
                sql_explanation=result.get("sql_explanation"),
                query_result=serialized_rows,
                columns=columns,
                row_count=row_count,
                chart_config=chart_config,
                insights=result.get("insights"),
                followup_questions=result.get("followup_questions"),
                error_message=error_message,
            )
        except Exception:
            logger.exception(
                "Unhandled error in analytics workflow for session=%s",
                request.session_uuid,
            )
            return AnalyticsResponse(
                question=request.question,
                error_message=_ERR_DATABASE,
            )
