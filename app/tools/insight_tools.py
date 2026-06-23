"""Insight tools module for the Natural Language Analytics Dashboard.

``InsightTools`` builds the single ``@tool``-decorated closure (``generate_insights``)
that the ``InsightAgent``'s ``create_agent()`` instance uses as its only internal tool.
The tool is constructed in ``__init__``, captures the injected LLM dep, and is stored
as an instance attribute so ``InsightAgent`` can pass it by name to ``create_agent``.

Contracts consumed: :class:`~app.orchestration.state.WorkflowState` (reads
``query_result`` and ``question`` fields).
Contracts produced: ``Command`` update with ``insights: list[str]`` written to
``WorkflowState.insights``.
"""

import json
from typing import Annotated

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from app.config.log_config import config as log_config
from app.orchestration.state import WorkflowState
from app.prompts.insight_prompt import INSIGHT_INNER_PROMPT
from app.schemas.insight_result import InsightOutput

logger = log_config.get_logger(__name__)

_MAX_INSIGHT_ROWS = 200


class InsightTools:
    """Builds and holds the ``generate_insights`` ``@tool`` closure for ``InsightAgent``.

    The LLM is injected via the constructor so the tool closure captures it
    without needing it passed as an argument at call time. ``InsightAgent``
    passes ``self.generate_insights`` directly to ``create_agent``::

        tools=[insight_tools.generate_insights]

    Args:
        llm: An LLM instance (``ChatGoogleGenerativeAI``) used for structured-output
            generation via ``llm.with_structured_output(InsightOutput)``.

    Attributes:
        generate_insights: The ``@tool``-decorated callable exposed to ``create_agent()``.
    """

    def __init__(self, llm) -> None:
        """Build the ``generate_insights`` tool, capturing ``llm`` in its closure.

        Args:
            llm: An LLM instance used for structured-output generation.
        """

        @tool
        def generate_insights(
            tool_call_id: Annotated[str, InjectedToolCallId],
            state: Annotated[WorkflowState, InjectedState()],
        ) -> Command:
            """Generate analytical insights from the query results in workflow state.

            Reads ``query_result`` and ``question`` from the injected ``WorkflowState``.
            If ``query_result`` is absent or has no rows, returns an empty insights list
            immediately without calling the LLM (non-critical path; insight generation
            should never fail the overall workflow).

            On LLM failure the exception is caught and an empty insights list is returned.
            ``error_message`` is never set by this tool — insight generation is
            non-critical and failures are silent from the supervisor's perspective.

            Args:
                tool_call_id: Injected LangGraph tool call identifier used to produce
                    a matching ``ToolMessage`` in the conversation history.
                state: Injected ``WorkflowState`` containing ``query_result`` and
                    ``question``.

            Returns:
                :class:`~langgraph.types.Command` with ``update`` dict containing
                ``insights: list[str]`` and a ``ToolMessage`` summarising the outcome.
            """
            query_result = state.get("query_result")
            question = state.get("question", "")

            if not query_result or not query_result.rows:
                logger.info("generate_insights: no data to analyze, skipping LLM call")
                return Command(
                    update={
                        "insights": [],
                        "messages": [
                            ToolMessage(
                                content="No data.",
                                tool_call_id=tool_call_id,
                            )
                        ],
                    }
                )

            try:
                rows = query_result.rows[:_MAX_INSIGHT_ROWS]
                if len(query_result.rows) > _MAX_INSIGHT_ROWS:
                    logger.warning(
                        "generate_insights: truncating %d rows to %d for prompt",
                        len(query_result.rows),
                        _MAX_INSIGHT_ROWS,
                    )
                rows_json = json.dumps(rows)
                prompt = INSIGHT_INNER_PROMPT.format(
                    question=question,
                    rows_json=rows_json,
                )
                result: InsightOutput = llm.with_structured_output(
                    InsightOutput
                ).invoke([HumanMessage(content=prompt)])
                logger.info(
                    "generate_insights: generated %d insights", len(result.insights)
                )
                return Command(
                    update={
                        "insights": result.insights,
                        "messages": [
                            ToolMessage(
                                content=f"Generated {len(result.insights)} insights.",
                                tool_call_id=tool_call_id,
                            )
                        ],
                    }
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("generate_insights: LLM call failed: %s", exc)
                return Command(
                    update={
                        "insights": [],
                        "messages": [
                            ToolMessage(
                                content="Insight generation failed.",
                                tool_call_id=tool_call_id,
                            )
                        ],
                    }
                )

        self.generate_insights = generate_insights
