"""Analytics graph assembly.

``AnalyticsGraph`` builds a plain LangGraph ``StateGraph`` that routes directly
to the SQL Agent subagent and returns the compiled ``CompiledStateGraph``.

Using a bare ``StateGraph`` instead of a third-party supervisor library keeps
the graph explicit and avoids version-compatibility issues. The SQL Agent is
added as a subgraph node; its internal tools (``generate_sql``, ``validate_sql``,
``execute_sql``, ``handle_unidentifiable``) are invisible at the outer graph
level. When issues #6–#8 add the Visualization, Insight, and Follow-Up agents,
an explicit supervisor node will be added to route between them in parallel.
"""

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents.sql_agent import SqlAgent
from app.config.env_config import settings
from app.config.log_config import config as log_config
from app.orchestration.state import WorkflowState

logger = log_config.get_logger(__name__)


class AnalyticsGraph:
    """Builds the compiled ``StateGraph`` over the agent subagents.

    ``build()`` instantiates ``SqlAgent`` and adds its compiled agent as a
    subgraph node, then compiles and returns the graph.

    Attributes:
        _llm: Chat model passed through to the SQL Agent.
        _retry_limit: Self-correction attempt bound forwarded to ``SqlAgent``.
    """

    def __init__(
        self,
        llm: ChatGoogleGenerativeAI,
        retry_limit: int | None = None,
    ) -> None:
        """Store dependencies used to assemble the graph.

        Args:
            llm: Chat model driving the SQL Agent.
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

        Adds ``SqlAgent`` as a subgraph node named ``"sql_agent"``. The SQL
        Agent's internal tools (``generate_sql``, ``validate_sql``,
        ``execute_sql``, ``handle_unidentifiable``) are encapsulated inside the
        subgraph and invisible at the outer graph level.

        Returns:
            The compiled ``StateGraph``, ready to ``invoke`` with a
            ``WorkflowState`` containing the user question.
        """
        sql_agent = SqlAgent(self._llm, retry_limit=self._retry_limit)
        logger.info("Building analytics graph with sql_agent subgraph node")

        builder = StateGraph(WorkflowState)
        builder.add_node("sql_agent", sql_agent._agent)
        builder.set_entry_point("sql_agent")
        builder.add_edge("sql_agent", END)

        graph = builder.compile()
        logger.info("Analytics graph compiled successfully")
        return graph
