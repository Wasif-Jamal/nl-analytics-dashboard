"""Analytics supervisor graph assembly.

``AnalyticsGraph`` assembles the capability tools and returns the compiled
LangChain ``create_agent`` supervisor (SDS §7). ``create_agent`` builds the
agent node, the prebuilt ``ToolNode``, and the routing internally — there are no
hand-written nodes or edges. For issue #1 the supervisor is configured with only
the ``query_database`` tool; visualization, insight, and follow-up tools are
appended to the same list in later issues without structural change.
"""

from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph.state import CompiledStateGraph

from app.agents.sql_agent import SqlAgent
from app.config.env_config import settings
from app.config.log_config import config as log_config
from app.orchestration.state import WorkflowState
from app.prompts.orchestrator_prompt import ORCHESTRATOR_PROMPT
from app.services.sql_service import QueryService

logger = log_config.get_logger(__name__)


class AnalyticsGraph:
    """Builds the compiled ``create_agent`` supervisor over the agent tools."""

    def __init__(
        self,
        llm: ChatGoogleGenerativeAI,
        query_service: QueryService,
        retry_limit: int | None = None,
    ) -> None:
        """Store the dependencies used to assemble the supervisor.

        Args:
            llm: The chat model driving the supervisor (and the inner SQL agent).
            query_service: Execution service injected into the SQL agent.
            retry_limit: Self-correction attempt bound for the SQL agent. Defaults
                to ``settings.sql_retry_limit`` (the ``SQL_RETRY_LIMIT`` env var).
        """
        self._llm = llm
        self._query_service = query_service
        self._retry_limit = (
            retry_limit if retry_limit is not None else settings.sql_retry_limit
        )
        logger.info("AnalyticsGraph configured (retry_limit=%d)", self._retry_limit)

    def build(self) -> CompiledStateGraph:
        """Assemble the tools and return the compiled supervisor graph.

        Returns:
            The compiled ``create_agent`` graph, ready to ``invoke`` with a
            ``WorkflowState`` containing the user ``question``.
        """
        sql_agent = SqlAgent(self._llm, self._query_service, self._retry_limit)
        tools = sql_agent.get_tools()
        tool_names = [t.name for t in tools]
        logger.info(
            "Building analytics supervisor with %d tool(s): %s", len(tools), tool_names
        )
        graph = create_agent(
            model=self._llm,
            tools=tools,
            system_prompt=ORCHESTRATOR_PROMPT,
            state_schema=WorkflowState,
        )
        logger.info("Supervisor graph compiled successfully")
        return graph
