"""VisualizationAgent — ``create_agent()`` subagraph with a private state schema.

``VisualizationAgent`` uses a private ``VisualizationAgentState`` so the model
starts with a clean message history (just a system prompt and a single
HumanMessage trigger). This avoids the "completed-conversation" problem: after
the SQL Agent finishes, ``WorkflowState.messages`` contains the full SQL pipeline
exchange, causing the model to see the task as already done and decline to call
any tool.

The ``node()`` method is registered in the outer ``StateGraph`` as
``"visualization_agent"``. It constructs a fresh ``VisualizationAgentState``,
invokes the compiled ``create_agent`` subgraph, and propagates only
``chart_config`` back to ``WorkflowState``.

Contracts consumed: ``WorkflowState.query_result`` (``QueryResult``) and
``WorkflowState.question``. Contract produced: ``WorkflowState.chart_config``
(``ChartConfig``).
"""

from typing import Optional

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import MessagesState

from app.config.log_config import config as log_config
from app.orchestration.state import WorkflowState
from app.prompts.visualization_prompt import VISUALIZATION_SYSTEM_PROMPT
from app.schemas.chart_config import ChartConfig
from app.schemas.sql_result import QueryResult
from app.tools.visualization_tools import VisualizationTools

logger = log_config.get_logger(__name__)


class VisualizationAgentState(MessagesState):
    """Private state for VisualizationAgent's ``create_agent`` loop.

    Holds only the fields ``select_visualization`` needs. ``messages`` is
    inherited from ``MessagesState`` and always starts fresh when ``node()``
    constructs the initial state — it never inherits ``WorkflowState.messages``.

    Attributes:
        question: The user's natural-language question.
        query_result: Executed query result read by ``select_visualization`` via
            ``InjectedState``.
        chart_config: Populated by ``select_visualization``; propagated to
            ``WorkflowState`` by ``node()``.
    """

    question: str
    query_result: Optional[QueryResult]
    chart_config: Optional[ChartConfig]


class VisualizationAgent:
    """VisualizationAgent — ``create_agent()`` instance with a private state schema.

    The compiled agent is **not** added directly to the outer graph as a
    subgraph. Instead, ``node()`` bridges the two states: it extracts the
    relevant fields from ``WorkflowState``, invokes ``_agent`` with a fresh
    ``VisualizationAgentState``, and returns only the ``chart_config`` update.

    Attributes:
        _agent: Compiled ``create_agent`` graph with ``VisualizationAgentState``
            as its state schema.
    """

    def __init__(self, llm: ChatGoogleGenerativeAI) -> None:
        """Build the VisualizationAgent ``create_agent`` instance.

        Args:
            llm: Chat model driving the ReAct loop and the nested
                structured-output call inside ``select_visualization``.
        """
        logger.info("VisualizationAgent initializing")
        viz_tools = VisualizationTools(llm=llm)
        self._agent = create_agent(
            model=llm,
            tools=[viz_tools.select_visualization],
            system_prompt=VISUALIZATION_SYSTEM_PROMPT,
            state_schema=VisualizationAgentState,
            name="visualization_agent",
        )
        logger.info("VisualizationAgent compiled")

    def node(self, state: WorkflowState) -> dict:
        """Invoke the visualization agent as an outer-graph node.

        Builds a fresh ``VisualizationAgentState`` from the relevant
        ``WorkflowState`` fields so the model sees only a clean pending task —
        not the full SQL conversation. Returns only the ``chart_config`` update
        so ``WorkflowState`` is not polluted with the agent's internal messages.

        Args:
            state: Current ``WorkflowState`` supplied by the outer graph.

        Returns:
            Dict with ``chart_config: ChartConfig | None`` (``None`` on no data
            or LLM failure — visualization errors are non-fatal).
        """
        logger.debug("VisualizationAgent node called")
        result = self._agent.invoke(
            {
                "messages": [HumanMessage(content="Select the best visualization.")],
                "question": state.get("question", ""),
                "query_result": state.get("query_result"),
            }
        )
        return {"chart_config": result.get("chart_config")}
