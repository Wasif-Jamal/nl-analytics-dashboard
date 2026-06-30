"""InsightAgent — ``create_agent()`` subagraph with a private state schema.

``InsightAgent`` uses a private ``InsightAgentState`` so the model starts with
a clean message history (just a system prompt and a single HumanMessage trigger).
This avoids the "completed-conversation" problem that occurs when ``state_schema``
is ``WorkflowState``: after the SQL Agent finishes, ``WorkflowState.messages``
contains the full SQL pipeline exchange, causing the model to see the task as
already done and decline to call any tool.

The ``node()`` method is registered in the outer ``StateGraph`` as
``"insight_agent"``. It constructs a fresh ``InsightAgentState``, invokes the
compiled ``create_agent`` subgraph, and propagates only ``insights`` back to
``WorkflowState``.

Contracts consumed: ``WorkflowState.query_result`` (``QueryResult``) and
``WorkflowState.question``. Contract produced: ``WorkflowState.insights``
(``list[str]``).
"""

from typing import Optional

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import MessagesState

from app.config.log_config import config as log_config
from app.orchestration.state import WorkflowState
from app.prompts.insight_prompt import INSIGHT_SYSTEM_PROMPT
from app.schemas.conversation import ConversationTurn
from app.schemas.sql_result import QueryResult
from app.tools.insight_tools import InsightTools

logger = log_config.get_logger(__name__)


class InsightAgentState(MessagesState):
    """Private state for InsightAgent's ``create_agent`` loop.

    Holds only the fields ``generate_insights`` needs. ``messages`` is
    inherited from ``MessagesState`` and always starts fresh when ``node()``
    constructs the initial state — it never inherits ``WorkflowState.messages``.

    Attributes:
        question: The user's natural-language question.
        query_result: Executed query result read by ``generate_insights`` via
            ``InjectedState``.
        conversation_history: Prior successful turns for the current session,
            forwarded from ``WorkflowState`` by ``node()``.
        insights: Populated by ``generate_insights``; propagated to
            ``WorkflowState`` by ``node()``.
    """

    question: str
    query_result: Optional[QueryResult]
    conversation_history: Optional[list[ConversationTurn]]
    insights: Optional[list[str]]


class InsightAgent:
    """InsightAgent — ``create_agent()`` instance with a private ``InsightAgentState``.

    The compiled agent is **not** added directly to the outer graph as a
    subgraph. Instead, ``node()`` bridges the two states: it extracts the
    relevant fields from ``WorkflowState``, invokes ``_agent`` with a fresh
    ``InsightAgentState``, and returns only the ``insights`` update.

    Attributes:
        _agent: Compiled ``create_agent`` graph with ``InsightAgentState`` as
            its state schema.
    """

    def __init__(self, llm: ChatGoogleGenerativeAI) -> None:
        """Build the InsightAgent ``create_agent`` instance.

        Args:
            llm: Chat model driving the ReAct loop and the nested
                structured-output call inside ``generate_insights``.
        """
        logger.info("InsightAgent initializing")
        insight_tools = InsightTools(llm=llm)
        self._agent = create_agent(
            model=llm,
            tools=[insight_tools.generate_insights],
            system_prompt=INSIGHT_SYSTEM_PROMPT,
            state_schema=InsightAgentState,
            name="insight_agent",
        )
        logger.info("InsightAgent compiled")

    def node(self, state: WorkflowState) -> dict:
        """Invoke the insight agent as an outer-graph node.

        Builds a fresh ``InsightAgentState`` from the relevant ``WorkflowState``
        fields so the model sees only a clean pending task — not the full SQL
        conversation. Returns only the ``insights`` update so ``WorkflowState``
        is not polluted with the agent's internal messages.

        Args:
            state: Current ``WorkflowState`` supplied by the outer graph.

        Returns:
            Dict with ``insights: list[str]`` (empty list on no data or LLM
            failure — insight errors are non-fatal).
        """
        logger.debug("InsightAgent node called")
        result = self._agent.invoke(
            {
                "messages": [HumanMessage(content="Analyze the query results.")],
                "question": state.get("question", ""),
                "query_result": state.get("query_result"),
                "conversation_history": state.get("conversation_history") or [],
            }
        )
        return {"insights": result.get("insights")}
