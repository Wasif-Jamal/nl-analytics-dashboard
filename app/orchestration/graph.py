"""Analytics graph assembly.

``AnalyticsGraph`` builds a plain LangGraph ``StateGraph`` that routes from the
SQL Agent to the Visualization Agent and returns the compiled
``CompiledStateGraph``.

Graph shape: ``START → sql_agent → [route_after_sql] → visualization_agent → END``

Using a bare ``StateGraph`` instead of a third-party supervisor library keeps
the graph explicit and avoids version-compatibility issues. Each agent is added
as a subgraph node; its internal tools are invisible at the outer graph level.
If the SQL Agent sets ``error_message``, ``route_after_sql`` short-circuits
directly to ``END``, skipping the Visualization Agent.
"""

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.sql_agent import SqlAgent
from app.agents.visualization_agent import VisualizationAgent
from app.config.env_config import settings
from app.config.log_config import config as log_config
from app.orchestration.state import WorkflowState

logger = log_config.get_logger(__name__)


def route_after_sql(state: WorkflowState) -> str:
    """Route after SQL Agent: to visualization if successful, else END.

    Args:
        state: Current ``WorkflowState`` after the SQL Agent has run.

    Returns:
        ``"visualization_agent"`` when the SQL Agent completed without an
        ``error_message``; ``END`` otherwise so the graph terminates early.
    """
    if state.get("error_message"):
        return END
    return "visualization_agent"


class AnalyticsGraph:
    """Builds the compiled ``StateGraph`` over the agent subagents.

    ``build()`` instantiates ``SqlAgent`` and ``VisualizationAgent``, adds each
    as a subgraph node, wires the conditional routing edge after ``sql_agent``,
    and compiles and returns the graph.

    Graph shape: ``START → sql_agent → [route_after_sql] → visualization_agent → END``

    Attributes:
        _llm: Chat model passed through to the agent subgraphs.
        _retry_limit: Self-correction attempt bound forwarded to ``SqlAgent``.
    """

    def __init__(
        self,
        llm: ChatGoogleGenerativeAI,
        retry_limit: int | None = None,
    ) -> None:
        """Store dependencies used to assemble the graph.

        Args:
            llm: Chat model driving the SQL Agent and Visualization Agent.
            retry_limit: Self-correction attempt bound for the SQL Agent.
                Defaults to ``settings.sql_retry_limit``.
        """
        self._llm = llm
        self._retry_limit = (
            retry_limit if retry_limit is not None else settings.sql_retry_limit
        )
        logger.info("AnalyticsGraph configured (retry_limit=%d)", self._retry_limit)

    def build(self) -> CompiledStateGraph:
        """Assemble the agent subagraphs and return the compiled graph.

        Adds ``SqlAgent`` as a subgraph node named ``"sql_agent"`` and
        ``VisualizationAgent`` as a subgraph node named
        ``"visualization_agent"``. Each agent's internal tools are encapsulated
        inside its subgraph and invisible at the outer graph level.
        ``route_after_sql`` provides the conditional edge: on success the graph
        proceeds to ``visualization_agent``; on error it terminates at ``END``.

        Returns:
            The compiled ``StateGraph``, ready to ``invoke`` with a
            ``WorkflowState`` containing the user question.
        """
        sql_agent = SqlAgent(self._llm, retry_limit=self._retry_limit)
        logger.info("Building analytics graph with sql_agent subgraph node")

        visualization_agent = VisualizationAgent(self._llm)
        logger.info("Adding visualization_agent subgraph node to analytics graph")

        builder = StateGraph(WorkflowState)
        builder.add_node("sql_agent", sql_agent._agent)
        builder.set_entry_point("sql_agent")
        builder.add_conditional_edges("sql_agent", route_after_sql)
        builder.add_node("visualization_agent", visualization_agent._agent)
        builder.add_edge("visualization_agent", END)

        graph = builder.compile()
        logger.info("Analytics graph compiled successfully")
        return graph
