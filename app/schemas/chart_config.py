"""Pydantic contracts for the visualization pipeline.

``ChartType`` enumerates the supported Plotly chart types and the explicit
table-only fallback. ``ChartConfig`` is the structured output produced by the
``VisualizationAgent`` and written to ``WorkflowState.chart_config`` via
``Command``. Agents communicate via typed schemas only — never unstructured
text (AGENTS.md §8).
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class ChartType(str, Enum):
    """Supported visualization types as defined in FRS §6.3."""

    bar = "bar"
    line = "line"
    pie = "pie"
    scatter = "scatter"
    table = "table"


class ChartConfig(BaseModel):
    """Visualization configuration produced by the VisualizationAgent.

    Used as the ``with_structured_output`` target inside ``select_visualization``
    and as the typed ``WorkflowState.chart_config`` field. Serialized to a plain
    dict (via ``.model_dump()``) by ``ChatService`` before building
    ``AnalyticsResponse``.

    Attributes:
        chart_type: Selected visualization type (bar / line / pie / scatter /
            table). ``"table"`` is the explicit fallback for ambiguous results
            and the single-scalar path.
        x_column: Column name for the x-axis, category axis, or pie labels.
            ``None`` for the table-only path.
        y_column: Column name for the y-axis, measure, or pie values.
            ``None`` for the table-only path.
        title: Short descriptive chart title; empty string when not applicable.
        written_answer: Plain-language sentence for single-value (1×1) results
            (e.g. "Total revenue for Q1 2025 is $842,000"). Set only when
            ``chart_type="table"`` and the result is a single scalar.
    """

    chart_type: ChartType
    x_column: Optional[str] = None
    y_column: Optional[str] = None
    title: str = ""
    written_answer: Optional[str] = None
