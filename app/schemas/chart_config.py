"""Pydantic contract for visualization configuration.

``ChartConfig`` is the typed schema the Visualization Agent writes to
``WorkflowState.chart_config`` via a ``Command`` update.  Downstream consumers
(Streamlit UI, tests) read this schema directly — never unstructured dicts
(AGENTS.md §6).

Fields:
    chart_type: One of the six supported display modes.
    x: Column name for the x-axis (bar/line/scatter) or the labels column (pie).
        None for single_value and table.
    y: Column name for the y-axis (bar/line/scatter) or the values column (pie).
        None for single_value and table.
    title: Human-readable chart title, always present.
    sentence: Plain-language answer; populated only for the single_value type.
"""

from typing import Literal, Optional

from pydantic import BaseModel


class ChartConfig(BaseModel):
    """Visualization configuration produced by the Visualization Agent.

    Pydantic contract for the chart the Streamlit UI renders.  The
    ``chart_type`` field drives which Plotly call is made; ``x`` and ``y``
    map to the relevant DataFrame columns.

    Attributes:
        chart_type: Display mode — one of bar, line, pie, scatter, table,
            single_value.
        x: X-axis / labels column name, or None when not applicable.
        y: Y-axis / values column name, or None when not applicable.
        title: Chart or card title shown in the UI.
        sentence: Plain-language answer string; present only for single_value.
    """

    chart_type: Literal["bar", "line", "pie", "scatter", "table", "single_value"]
    x: Optional[str] = None
    y: Optional[str] = None
    title: str
    sentence: Optional[str] = None
