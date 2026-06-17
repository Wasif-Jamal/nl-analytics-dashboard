"""LangGraph node: translate a natural-language question into SQL.

Reads ``question`` from workflow state, delegates to :class:`SqlAgent`, and
writes ``generated_sql`` / ``sql_explanation`` back into state. Sets
``error_message`` when the question cannot be mapped to schema entities or
when the LLM call fails.
"""

from app.agents.sql_agent import SqlAgent
from app.config.log_config import get_logger
from app.orchestration.state import WorkflowState

logger = get_logger(__name__)

_ENTITY_ERROR = "Unable to identify requested entities."


class SqlGenerationNode:
    """LangGraph node that calls SqlAgent and writes SQL into workflow state.

    Consumed by the LangGraph graph (``app/orchestration/graph.py``) as a
    callable node. Sets ``error_message`` on any failure path so downstream
    conditional edges can route to the response node without executing SQL.
    """

    def __init__(self, agent: SqlAgent | None = None) -> None:
        """Initialise the node with a SQL agent.

        Args:
            agent: Injected :class:`SqlAgent`. Defaults to a fresh ``SqlAgent()``
                when not provided; useful for passing mocks in tests.
        """
        self._agent = agent or SqlAgent()

    def __call__(self, state: WorkflowState) -> WorkflowState:
        """Generate SQL for ``state["question"]`` and return updated state.

        Args:
            state: Current workflow state containing at least ``question``.

        Returns:
            Updated state with ``generated_sql`` + ``sql_explanation`` on
            success, or ``error_message`` set on failure.
        """
        logger.info("SqlGenerationNode: processing question: %s", state["question"])
        try:
            output = self._agent.generate(state["question"])
            if not output.is_identifiable:
                logger.warning(
                    "SqlGenerationNode: question not identifiable: %s",
                    state["question"],
                )
                return {**state, "error_message": _ENTITY_ERROR}
            logger.info("SqlGenerationNode: SQL generated successfully")
            return {
                **state,
                "generated_sql": output.sql,
                "sql_explanation": output.explanation,
            }
        except Exception:
            logger.exception(
                "SqlGenerationNode: unexpected error for question: %s",
                state["question"],
            )
            return {**state, "error_message": _ENTITY_ERROR}
