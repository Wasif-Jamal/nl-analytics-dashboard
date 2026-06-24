"""Visualization tools module for the Natural Language Analytics Dashboard.

``VisualizationTools`` builds the single ``@tool``-decorated closure
(``select_visualization``) that the ``VisualizationAgent``'s ``create_agent()``
instance uses as its only internal tool. The tool is constructed in ``__init__``,
captures the injected LLM dep, and is stored as an instance attribute so
``VisualizationAgent`` can pass it by name to ``create_agent``.

Contracts consumed: ``VisualizationAgentState`` (reads ``query_result`` and
``question`` fields via the minimal ``_VisualizationToolState`` TypedDict —
avoids Pydantic validation errors when the tool runs under the private agent
state rather than ``WorkflowState``).
Contracts produced: ``Command`` update with ``chart_config: ChartConfig`` written
to the agent state, propagated to ``WorkflowState.chart_config`` by
``VisualizationAgent.node()``.
"""

import json
from typing import Annotated, Optional, TypedDict

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from app.config.log_config import config as log_config
from app.prompts.visualization_prompt import VISUALIZATION_INNER_PROMPT
from app.schemas.chart_config import ChartConfig
from app.schemas.sql_result import QueryResult

logger = log_config.get_logger(__name__)

_MAX_VIZ_ROWS = 10


class _VisualizationToolState(TypedDict, total=False):
    """Minimal state shape injected into ``select_visualization`` by LangGraph.

    Only the two fields the tool reads are declared; ``total=False`` so Pydantic
    never complains about unset fields when the tool is called with
    ``VisualizationAgentState``.
    """

    question: str
    query_result: Optional[QueryResult]


class VisualizationTools:
    """Builds and holds the ``select_visualization`` ``@tool`` closure.

    The LLM is injected via the constructor so the tool closure captures it
    without needing it passed as an argument at call time. ``VisualizationAgent``
    passes ``self.select_visualization`` directly to ``create_agent``::

        tools=[viz_tools.select_visualization]

    Args:
        llm: An LLM instance used for structured-output generation via
            ``llm.with_structured_output(ChartConfig)``.

    Attributes:
        select_visualization: The ``@tool``-decorated callable exposed to
            ``create_agent()``.
    """

    def __init__(self, llm) -> None:
        """Build the ``select_visualization`` tool, capturing ``llm`` in its closure.

        Args:
            llm: An LLM instance used for structured-output generation.
        """

        @tool
        def select_visualization(
            tool_call_id: Annotated[str, InjectedToolCallId],
            state: Annotated[_VisualizationToolState, InjectedState()],
        ) -> Command:
            """Select the best visualization type for the query results.

            Reads ``query_result`` and ``question`` from the injected
            ``VisualizationAgentState`` (typed as the minimal
            ``_VisualizationToolState`` to avoid Pydantic validation errors under
            the private agent state). Rows are capped at ``_MAX_VIZ_ROWS = 10``
            before serialization. Returns a ``ChartConfig`` via ``Command``.

            If ``query_result`` is absent or empty, returns ``chart_config=None``
            without calling the LLM. On LLM failure, logs the error and returns
            ``chart_config=None``; ``error_message`` is never set (visualization
            is non-fatal).

            Args:
                tool_call_id: Injected LangGraph tool call identifier for the
                    matching ``ToolMessage``.
                state: Injected ``_VisualizationToolState`` with ``query_result``
                    and ``question``.

            Returns:
                :class:`~langgraph.types.Command` with ``chart_config``
                (``ChartConfig`` or ``None``) and a ``ToolMessage`` summary.
            """
            query_result = state.get("query_result")
            question = state.get("question", "")

            if not query_result or not query_result.rows:
                logger.info(
                    "select_visualization: no data to analyze, skipping LLM call"
                )
                return Command(
                    update={
                        "chart_config": None,
                        "messages": [
                            ToolMessage(content="No data.", tool_call_id=tool_call_id)
                        ],
                    }
                )

            try:
                rows = query_result.rows[:_MAX_VIZ_ROWS]
                if len(query_result.rows) > _MAX_VIZ_ROWS:
                    logger.warning(
                        "select_visualization: truncating %d rows to %d for prompt",
                        len(query_result.rows),
                        _MAX_VIZ_ROWS,
                    )
                prompt = VISUALIZATION_INNER_PROMPT.format(
                    question=question,
                    columns=", ".join(query_result.columns),
                    row_count=query_result.row_count,
                    rows_json=json.dumps(rows),
                )
                result: ChartConfig = llm.with_structured_output(ChartConfig).invoke(
                    [HumanMessage(content=prompt)]
                )
                logger.info(
                    "select_visualization: selected chart_type=%s", result.chart_type
                )
                return Command(
                    update={
                        "chart_config": result,
                        "messages": [
                            ToolMessage(
                                content=f"Selected chart_type={result.chart_type}.",
                                tool_call_id=tool_call_id,
                            )
                        ],
                    }
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("select_visualization: LLM call failed: %s", exc)
                return Command(
                    update={
                        "chart_config": None,
                        "messages": [
                            ToolMessage(
                                content="Visualization selection failed.",
                                tool_call_id=tool_call_id,
                            )
                        ],
                    }
                )

        self.select_visualization = select_visualization
