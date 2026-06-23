"""Visualization tools provided to VisualizationAgent.

``VisualizationTools`` builds the three ``@tool``-decorated closures the
``VisualizationAgent``'s ``create_agent()`` instance uses as internal tools.
All three are constructed in ``__init__`` and stored as instance attributes so
``VisualizationAgent`` can pass them by name to ``create_agent``.

Contracts consumed/produced: :class:`~app.schemas.sql_result.QueryResult`
(read from ``WorkflowState.query_result`` via ``InjectedState``) and
:class:`~app.schemas.chart_config.ChartConfig` (written to
``WorkflowState.chart_config`` via ``Command`` by ``build_chart_config`` and
``build_sentence``).
"""

from typing import Annotated, Optional

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from app.config.log_config import config as log_config
from app.orchestration.state import WorkflowState
from app.schemas.chart_config import ChartConfig
from app.utils.chart_helpers import classify_shape

logger = log_config.get_logger(__name__)


class VisualizationTools:
    """Builds the three internal tools for ``VisualizationAgent``.

    All tools are ``@tool``-decorated closures defined in ``__init__`` and
    exposed as instance attributes.  ``VisualizationAgent`` passes them
    directly to ``create_agent``::

        tools=[
            viz_tools.analyze_shape,
            viz_tools.build_chart_config,
            viz_tools.build_sentence,
        ]

    ``analyze_shape`` reads ``WorkflowState`` via ``InjectedState`` (auto-injected
    by LangGraph) and returns a classification dict as feedback to the LLM.
    ``build_chart_config`` and ``build_sentence`` write
    :class:`~app.schemas.chart_config.ChartConfig` to ``WorkflowState.chart_config``
    via ``Command``.

    No constructor dependencies are required because LangGraph injects state
    automatically.
    """

    def __init__(self) -> None:
        """Build three ``@tool`` closures and expose as instance attributes."""

        @tool
        def analyze_shape(
            state: Annotated[WorkflowState, InjectedState],
        ) -> dict:
            """Analyze the query_result shape to determine chart type and column mapping.

            Reads ``WorkflowState.query_result`` (auto-injected by LangGraph via
            ``InjectedState``) and calls
            :func:`~app.utils.chart_helpers.classify_shape` to classify the result.
            Returns feedback to the LLM only — does NOT write to ``WorkflowState``.

            Args:
                state: Auto-injected ``WorkflowState``; the LLM passes no arguments.

            Returns:
                dict with keys ``chart_type``, ``x``, and ``y``.  ``chart_type`` is
                one of ``bar``, ``line``, ``pie``, ``scatter``, ``table``, or
                ``single_value``.  ``x`` and ``y`` are column-name strings or ``None``.
            """
            qr = state.get("query_result")
            if qr is None:
                logger.warning(
                    "analyze_shape: query_result is None, falling back to table"
                )
                return {"chart_type": "table", "x": None, "y": None}
            dtypes = {col: str(dtype) for col, dtype in qr.dataframe.dtypes.items()}
            result = classify_shape(qr.columns, dtypes, qr.row_count)
            logger.debug("analyze_shape: %s", result)
            return result

        @tool
        def build_chart_config(
            chart_type: str,
            title: str,
            x: Optional[str] = None,
            y: Optional[str] = None,
            *,
            tool_call_id: Annotated[str, InjectedToolCallId],
        ) -> Command:
            """Assemble a ChartConfig and write it to WorkflowState.

            Constructs a :class:`~app.schemas.chart_config.ChartConfig` from the
            LLM-supplied arguments (which must originate from ``analyze_shape``'s
            return) and writes it to ``WorkflowState.chart_config`` via a
            ``Command`` update.

            Args:
                chart_type: Plotly chart mode — one of ``bar``, ``line``, ``pie``,
                    ``scatter``, or ``table``.
                x: Column name for the x-axis / labels; may be ``None``.
                y: Column name for the y-axis / values; may be ``None``.
                title: Short human-readable chart title.
                tool_call_id: Injected id for the response ``ToolMessage``.

            Returns:
                :class:`~langgraph.types.Command` updating ``WorkflowState`` with
                the assembled :class:`~app.schemas.chart_config.ChartConfig`.
            """
            config = ChartConfig(chart_type=chart_type, x=x, y=y, title=title)
            logger.info("build_chart_config: chart_type=%s", chart_type)
            return Command(
                update={
                    "chart_config": config,
                    "messages": [
                        ToolMessage(
                            content=f"chart_type={chart_type} x={x} y={y}",
                            tool_call_id=tool_call_id,
                        )
                    ],
                }
            )

        @tool
        def build_sentence(
            sentence: str,
            title: str,
            tool_call_id: Annotated[str, InjectedToolCallId],
        ) -> Command:
            """Store a plain-language sentence for a single-value result.

            Constructs a :class:`~app.schemas.chart_config.ChartConfig` with
            ``chart_type="single_value"`` and the LLM-composed sentence, then
            writes it to ``WorkflowState.chart_config`` via a ``Command`` update.

            Args:
                sentence: Natural-language answer string composed by the LLM,
                    e.g. ``"Total revenue for this quarter is $200K USD."``.
                title: Short descriptive title for the display card.
                tool_call_id: Injected id for the response ``ToolMessage``.

            Returns:
                :class:`~langgraph.types.Command` updating ``WorkflowState`` with
                a single_value :class:`~app.schemas.chart_config.ChartConfig`.
            """
            config = ChartConfig(
                chart_type="single_value", title=title, sentence=sentence
            )
            logger.info("build_sentence: title=%r sentence=%.80s", title, sentence)
            return Command(
                update={
                    "chart_config": config,
                    "messages": [
                        ToolMessage(
                            content=f"single_value: {sentence[:80]}",
                            tool_call_id=tool_call_id,
                        )
                    ],
                }
            )

        self.analyze_shape = analyze_shape
        self.build_chart_config = build_chart_config
        self.build_sentence = build_sentence
