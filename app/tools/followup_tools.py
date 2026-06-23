"""Follow-up tools module for the Natural Language Analytics Dashboard.

``FollowupTools`` builds the single ``@tool``-decorated closure
(``generate_followup_questions``) that the ``FollowupAgent``'s ``create_agent()``
instance uses as its only internal tool.
The tool is constructed in ``__init__``, captures the injected LLM dep, and is stored
as an instance attribute so ``FollowupAgent`` can pass it by name to ``create_agent``.

Contracts consumed: ``FollowupAgentState`` (reads ``query_result`` and ``question``
fields via the minimal ``_FollowupToolState`` TypedDict — avoids Pydantic validation
errors when the tool is called under the private agent state rather than
``WorkflowState``).
Contracts produced: ``Command`` update with ``followup_questions: list[str]`` written
to the agent state, propagated to ``WorkflowState.followup_questions`` by
``FollowupAgent.node()``.
"""

import json
from typing import Annotated, Optional, TypedDict

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from app.config.log_config import config as log_config
from app.prompts.followup_prompt import FOLLOWUP_INNER_PROMPT
from app.schemas.followup_result import FollowupOutput
from app.schemas.sql_result import QueryResult


class _FollowupToolState(TypedDict, total=False):
    """Minimal state shape injected into ``generate_followup_questions`` by LangGraph.

    Only the two fields the tool reads are declared; ``total=False`` so Pydantic
    never complains about unset fields when the tool is called with
    ``FollowupAgentState``.
    """

    question: str
    query_result: Optional[QueryResult]


logger = log_config.get_logger(__name__)

# Follow-up generation needs data shape and representative patterns, not every row — 50 is sufficient and keeps prompt small.
_MAX_FOLLOWUP_ROWS = 50


class FollowupTools:
    """Builds and holds the ``generate_followup_questions`` ``@tool`` closure for ``FollowupAgent``.

    The LLM is injected via the constructor so the tool closure captures it
    without needing it passed as an argument at call time. ``FollowupAgent``
    passes ``self.generate_followup_questions`` directly to ``create_agent``::

        tools=[followup_tools.generate_followup_questions]

    Args:
        llm: An LLM instance (``ChatGoogleGenerativeAI``) used for structured-output
            generation via ``llm.with_structured_output(FollowupOutput)``.

    Attributes:
        generate_followup_questions: The ``@tool``-decorated callable exposed to
            ``create_agent()``.
    """

    def __init__(self, llm) -> None:
        """Build the ``generate_followup_questions`` tool, capturing ``llm`` in its closure.

        Args:
            llm: An LLM instance used for structured-output generation.
        """

        @tool
        def generate_followup_questions(
            tool_call_id: Annotated[str, InjectedToolCallId],
            state: Annotated[_FollowupToolState, InjectedState()],
        ) -> Command:
            """Generate follow-up questions grounded in the query results in workflow state.

            Reads ``query_result`` and ``question`` from the injected
            ``FollowupAgentState`` (typed here as the minimal ``_FollowupToolState``
            so Pydantic never requires fields that exist in ``WorkflowState`` but
            not in the private agent state).
            If ``query_result`` is absent or has no rows, returns an empty
            follow-up questions list immediately without calling the LLM.

            On LLM failure the exception is caught and an empty follow-up questions
            list is returned. ``error_message`` is never set — follow-up generation
            is non-critical.

            Args:
                tool_call_id: Injected LangGraph tool call identifier used to produce
                    a matching ``ToolMessage`` in the conversation history.
                state: Injected ``_FollowupToolState`` containing ``query_result`` and
                    ``question``.

            Returns:
                :class:`~langgraph.types.Command` with ``update`` dict containing
                ``followup_questions: list[str]`` and a ``ToolMessage`` summarising
                the outcome.
            """
            query_result = state.get("query_result")
            question = state.get("question", "")

            if not query_result or not query_result.rows:
                logger.info(
                    "generate_followup_questions: no data to analyze, skipping LLM call"
                )
                return Command(
                    update={
                        "followup_questions": [],
                        "messages": [
                            ToolMessage(
                                content="No data.",
                                tool_call_id=tool_call_id,
                            )
                        ],
                    }
                )

            try:
                rows = query_result.rows[:_MAX_FOLLOWUP_ROWS]
                if len(query_result.rows) > _MAX_FOLLOWUP_ROWS:
                    logger.warning(
                        "generate_followup_questions: truncating %d rows to %d for prompt",
                        len(query_result.rows),
                        _MAX_FOLLOWUP_ROWS,
                    )
                rows_json = json.dumps(rows)
                prompt = FOLLOWUP_INNER_PROMPT.format(
                    question=question,
                    rows_json=rows_json,
                )
                result: FollowupOutput = llm.with_structured_output(
                    FollowupOutput
                ).invoke([HumanMessage(content=prompt)])
                logger.info(
                    "generate_followup_questions: generated %d questions",
                    len(result.followup_questions),
                )
                return Command(
                    update={
                        "followup_questions": result.followup_questions,
                        "messages": [
                            ToolMessage(
                                content=f"Generated {len(result.followup_questions)} follow-up questions.",
                                tool_call_id=tool_call_id,
                            )
                        ],
                    }
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("generate_followup_questions: LLM call failed: %s", exc)
                return Command(
                    update={
                        "followup_questions": [],
                        "messages": [
                            ToolMessage(
                                content="Follow-up question generation failed.",
                                tool_call_id=tool_call_id,
                            )
                        ],
                    }
                )

        self.generate_followup_questions = generate_followup_questions
