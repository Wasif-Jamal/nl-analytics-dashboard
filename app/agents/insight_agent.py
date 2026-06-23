"""InsightAgent — a ``create_agent()`` subagent for FR-9 data-grounded insights.

``InsightAgent`` is a ``create_agent()`` instance whose sole internal tool is
``generate_insights`` (defined in ``InsightTools``). It is added to the outer
``StateGraph`` as a subgraph node named ``"insight_agent"``. Its internal tool
is invisible to the outer graph.

Contracts consumed: ``WorkflowState.query_result`` (``QueryResult``) and
``WorkflowState.question``. Contract produced: ``WorkflowState.insights``
(``list[str]``).
"""

from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI

from app.config.log_config import config as log_config
from app.orchestration.state import WorkflowState
from app.prompts.insight_prompt import INSIGHT_SYSTEM_PROMPT
from app.tools.insight_tools import InsightTools

logger = log_config.get_logger(__name__)


class InsightAgent:
    """InsightAgent — ``create_agent()`` instance with ``generate_insights`` internal tool.

    ``self._agent`` is the compiled ``create_agent`` graph, added to the outer
    ``StateGraph`` as a subgraph node named ``"insight_agent"``. Its internal
    tool is invisible to the outer graph.

    Attributes:
        _agent: Compiled ``create_agent`` graph driven by ``INSIGHT_SYSTEM_PROMPT``
            and ``InsightTools.generate_insights``.
    """

    def __init__(self, llm: ChatGoogleGenerativeAI) -> None:
        """Build the InsightAgent ``create_agent`` instance.

        Args:
            llm: Chat model driving the agent's ReAct loop and the nested
                ``generate_insights`` structured-output call.
        """
        logger.info("InsightAgent initializing")
        insight_tools = InsightTools(llm=llm)
        self._agent = create_agent(
            model=llm,
            tools=[insight_tools.generate_insights],
            system_prompt=INSIGHT_SYSTEM_PROMPT,
            state_schema=WorkflowState,
            name="insight_agent",
        )
        logger.info("InsightAgent compiled")
