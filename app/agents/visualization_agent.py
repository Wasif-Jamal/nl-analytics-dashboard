"""Visualization Agent — a ``create_agent()`` subagent with three internal tools.

``VisualizationAgent`` is a ``create_agent()`` instance whose internal tools
handle the full visualization pipeline: ``analyze_shape`` (classifies the query
result shape deterministically), ``build_chart_config`` (assembles a
:class:`~app.schemas.chart_config.ChartConfig` for multi-row data and writes it
to state), and ``build_sentence`` (stores a plain-language summary for
single-value results).

The compiled agent is exposed via ``self._agent`` and added to the outer
``StateGraph`` by ``AnalyticsGraph`` as a subgraph node named
``"visualization_agent"``. Its internal tools are invisible to the outer graph
(AGENTS.md §5, §6).

Contracts consumed/produced: :class:`~app.schemas.sql_result.QueryResult`
(read from ``WorkflowState.query_result``) and
:class:`~app.schemas.chart_config.ChartConfig` (written to
``WorkflowState.chart_config``).
"""

from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI

from app.config.log_config import config as log_config
from app.orchestration.state import WorkflowState
from app.prompts.visualization_prompt import VISUALIZATION_SYSTEM_PROMPT
from app.tools.visualization_tools import VisualizationTools

logger = log_config.get_logger(__name__)


class VisualizationAgent:
    """Visualization pipeline subagent — ``create_agent()`` instance with three tools.

    ``self._agent`` is the compiled ``create_agent`` graph, added to the outer
    ``StateGraph`` as a subgraph node. Its internal tools (``analyze_shape``,
    ``build_chart_config``, ``build_sentence``) are invisible to the outer graph.

    Attributes:
        _agent: Compiled ``create_agent`` graph produced by ``create_agent()``.
    """

    def __init__(self, llm: ChatGoogleGenerativeAI) -> None:
        """Build the Visualization Agent's ``create_agent`` instance with three tools.

        Instantiates :class:`~app.tools.visualization_tools.VisualizationTools`
        (which requires no injected deps — LangGraph auto-injects state) and calls
        ``create_agent`` to compile the agent graph.

        Args:
            llm: Chat model driving the Visualization Agent's ReAct loop.
        """
        logger.info("VisualizationAgent initializing")

        viz_tools = VisualizationTools()

        self._agent = create_agent(
            model=llm,
            tools=[
                viz_tools.analyze_shape,
                viz_tools.build_chart_config,
                viz_tools.build_sentence,
            ],
            system_prompt=VISUALIZATION_SYSTEM_PROMPT,
            state_schema=WorkflowState,
            name="visualization_agent",
        )

        logger.info("VisualizationAgent compiled")
