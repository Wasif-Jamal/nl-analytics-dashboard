"""Analytics graph assembly.

``AnalyticsGraph`` builds a plain LangGraph ``StateGraph`` that routes the
SQL Agent result through a conditional fan-out: on success it invokes
``VisualizationAgent``, ``InsightAgent``, and ``FollowupAgent`` in parallel;
on error it routes directly to ``END``. Using a bare ``StateGraph`` keeps the
graph explicit and avoids version-compatibility issues with third-party
supervisor libraries.
"""

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.followup_agent import FollowupAgent
from app.agents.insight_agent import InsightAgent
from app.agents.sql_agent import SqlAgent
from app.agents.visualization_agent import VisualizationAgent
from app.config.env_config import settings
from app.config.log_config import config as log_config
from app.orchestration.state import WorkflowState

logger = log_config.get_logger(__name__)


def _route_after_sql(state: WorkflowState) -> str | list[str]:
    """Route to END on error; fan-out to all three analysis nodes on success.

    Args:
        state: Current ``WorkflowState`` after the SQL Agent completes.

    Returns:
        ``END`` when ``error_message`` is set; otherwise a list of the three
        analysis node names for parallel fan-out.
    """
    if state.get("error_message"):
        return END
    return ["visualization_agent", "insight_agent", "followup_agent"]


class AnalyticsGraph:
    """Builds the compiled ``StateGraph`` over the agent subagents.

    ``build()`` instantiates all four agents and wires them into the graph:
    ``sql_agent`` at the entry point; a conditional fan-out to
    ``visualization_agent``, ``insight_agent``, and ``followup_agent`` in
    parallel on SQL success; direct route to ``END`` on SQL error.

    Attributes:
        _llm: Chat model passed through to all agents.
        _retry_limit: Self-correction attempt bound forwarded to ``SqlAgent``.
    """

    def __init__(
        self,
        llm: ChatGoogleGenerativeAI,
        retry_limit: int | None = None,
    ) -> None:
        """Store dependencies used to assemble the graph.

        Args:
            llm: Chat model driving all agents.
            retry_limit: Self-correction attempt bound for the SQL Agent.
                Defaults to ``settings.sql_retry_limit``.
        """
        self._llm = llm
        self._retry_limit = (
            retry_limit if retry_limit is not None else settings.sql_retry_limit
        )
        logger.info("AnalyticsGraph configured (retry_limit=%d)", self._retry_limit)

    def build(self) -> CompiledStateGraph:
        """Assemble the agent subgraphs and return the compiled graph.

        Constructs all four agents, adds them as nodes, wires the conditional
        fan-out from ``sql_agent``, and compiles the graph.

        Returns:
            The compiled ``StateGraph``, ready to ``invoke`` with a
            ``WorkflowState`` containing the user question.
        """
        sql_agent = SqlAgent(self._llm, retry_limit=self._retry_limit)
        viz_agent = VisualizationAgent(self._llm)
        insight_agent = InsightAgent(self._llm)
        followup_agent = FollowupAgent(self._llm)

        logger.info("Building analytics graph with four agent nodes")

        builder = StateGraph(WorkflowState)
        builder.add_node("sql_agent", sql_agent._agent)
        builder.add_node("visualization_agent", viz_agent.node)
        builder.add_node("insight_agent", insight_agent._agent)
        builder.add_node("followup_agent", followup_agent.node)

        builder.set_entry_point("sql_agent")
        builder.add_conditional_edges("sql_agent", _route_after_sql)
        builder.add_edge("visualization_agent", END)
        builder.add_edge("insight_agent", END)
        builder.add_edge("followup_agent", END)

        graph = builder.compile()
        logger.info("Analytics graph compiled (4 nodes + conditional fan-out)")
        return graph
