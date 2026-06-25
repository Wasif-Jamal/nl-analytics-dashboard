"""FollowupAgent — ``create_agent()`` subgraph with a private state schema.

``FollowupAgent`` uses a private ``FollowupAgentState`` so the model starts with
a clean message history (just a system prompt and a single HumanMessage trigger).
This avoids the "completed-conversation" problem that occurs when ``state_schema``
is ``WorkflowState``: after the SQL Agent finishes, ``WorkflowState.messages``
contains the full SQL pipeline exchange, causing the model to see the task as
already done and decline to call any tool.

The ``node()`` method is registered in the outer ``StateGraph`` as
``"followup_agent"``. It constructs a fresh ``FollowupAgentState``, invokes the
compiled ``create_agent`` subgraph, and propagates only ``followup_questions`` back
to ``WorkflowState``.

Contracts consumed: ``WorkflowState.question`` (``str``) and
``WorkflowState.query_result`` (``QueryResult``). Contract produced:
``WorkflowState.followup_questions`` (``list[str]``).
"""

from typing import Optional

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import MessagesState

from app.config.log_config import config as log_config
from app.orchestration.state import WorkflowState
from app.prompts.followup_prompt import FOLLOWUP_SYSTEM_PROMPT
from app.schemas.conversation import ConversationTurn
from app.schemas.sql_result import QueryResult
from app.tools.followup_tools import FollowupTools

logger = log_config.get_logger(__name__)


class FollowupAgentState(MessagesState):
    """Private state for FollowupAgent's ``create_agent`` loop.

    Holds only the fields ``generate_followup_questions`` needs. ``messages`` is
    inherited from ``MessagesState`` and always starts fresh when ``node()``
    constructs the initial state — it never inherits ``WorkflowState.messages``.

    Attributes:
        question: The user's natural-language question.
        query_result: Executed query result read by ``generate_followup_questions``
            via ``InjectedState``.
        conversation_history: Prior successful turns for the current session,
            forwarded from ``WorkflowState`` by ``node()``.
        followup_questions: Populated by ``generate_followup_questions``; propagated
            to ``WorkflowState`` by ``node()``.
    """

    question: str
    query_result: Optional[QueryResult]
    conversation_history: Optional[list[ConversationTurn]]
    followup_questions: Optional[list[str]]


class FollowupAgent:
    """FollowupAgent — ``create_agent()`` instance with a private ``FollowupAgentState``.

    The compiled agent is **not** added directly to the outer graph as a
    subgraph. Instead, ``node()`` bridges the two states: it extracts the
    relevant fields from ``WorkflowState``, invokes ``_agent`` with a fresh
    ``FollowupAgentState``, and returns only the ``followup_questions`` update.

    Attributes:
        _agent: Compiled ``create_agent`` graph with ``FollowupAgentState`` as
            its state schema.
    """

    def __init__(self, llm: ChatGoogleGenerativeAI) -> None:
        """Build the FollowupAgent ``create_agent`` instance.

        Args:
            llm: Chat model driving the ReAct loop and the nested
                structured-output call inside ``generate_followup_questions``.
        """
        logger.info("FollowupAgent initializing")
        followup_tools = FollowupTools(llm=llm)
        self._agent = create_agent(
            model=llm,
            tools=[followup_tools.generate_followup_questions],
            system_prompt=FOLLOWUP_SYSTEM_PROMPT,
            state_schema=FollowupAgentState,
            name="followup_agent",
        )
        logger.info("FollowupAgent compiled")

    def node(self, state: WorkflowState) -> dict:
        """Invoke the follow-up agent as an outer-graph node.

        Builds a fresh ``FollowupAgentState`` from the relevant ``WorkflowState``
        fields so the model sees only a clean pending task — not the full SQL
        conversation. Returns only the ``followup_questions`` update so
        ``WorkflowState`` is not polluted with the agent's internal messages.

        Args:
            state: Current ``WorkflowState`` supplied by the outer graph.

        Returns:
            Dict with ``followup_questions: list[str]`` (empty list on no data or
            LLM failure — follow-up generation errors are non-fatal).
        """
        logger.debug("FollowupAgent node called")
        result = self._agent.invoke(
            {
                "messages": [
                    HumanMessage(
                        content="Suggest follow-up questions for the query results."
                    )
                ],
                "question": state.get("question", ""),
                "query_result": state.get("query_result"),
                "conversation_history": state.get("conversation_history") or [],
            }
        )
        return {"followup_questions": result.get("followup_questions")}
