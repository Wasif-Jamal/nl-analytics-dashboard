"""Unit tests for app.utils.chart_helpers.build_figure.

Tests cover all chart types, the table-only None path, missing column guard,
and empty rows guard. No mocks needed — pure function with real Plotly figures.

Covers spec scenarios: bar chart built, line/pie/scatter built, table returns
None, missing column returns None, empty rows returns None.
"""

import plotly.graph_objects as go

from app.schemas.chart_config import ChartConfig, ChartType
from app.utils.chart_helpers import build_figure

_ROWS = [
    {"region": "East", "sales": 1000.0},
    {"region": "West", "sales": 800.0},
    {"region": "South", "sales": 600.0},
]

_TWO_NUM_ROWS = [
    {"revenue": 1000.0, "profit": 200.0},
    {"revenue": 800.0, "profit": 150.0},
]

_SCALAR_ROW = [{"total_revenue": 2500.0}]


# ---------------------------------------------------------------------------
# Chart type success paths
# ---------------------------------------------------------------------------


def test_build_figure_bar():
    """Returns a Figure for chart_type='bar' with valid rows."""
    config = ChartConfig(
        chart_type=ChartType.bar,
        x_column="region",
        y_column="sales",
        title="Sales by Region",
    )
    fig = build_figure(config, _ROWS)
    assert isinstance(fig, go.Figure)


def test_build_figure_line():
    """Returns a Figure for chart_type='line' with valid rows."""
    config = ChartConfig(
        chart_type=ChartType.line,
        x_column="region",
        y_column="sales",
        title="Sales Trend",
    )
    fig = build_figure(config, _ROWS)
    assert isinstance(fig, go.Figure)


def test_build_figure_pie():
    """Returns a Figure for chart_type='pie' with valid rows."""
    config = ChartConfig(
        chart_type=ChartType.pie,
        x_column="region",
        y_column="sales",
        title="Sales Share",
    )
    fig = build_figure(config, _ROWS)
    assert isinstance(fig, go.Figure)


def test_build_figure_scatter():
    """Returns a Figure for chart_type='scatter' with valid rows."""
    config = ChartConfig(
        chart_type=ChartType.scatter,
        x_column="revenue",
        y_column="profit",
        title="Revenue vs Profit",
    )
    fig = build_figure(config, _TWO_NUM_ROWS)
    assert isinstance(fig, go.Figure)


# ---------------------------------------------------------------------------
# None paths
# ---------------------------------------------------------------------------


def test_build_figure_table_returns_none():
    """Returns None for chart_type='table' regardless of row contents."""
    config = ChartConfig(chart_type=ChartType.table)
    fig = build_figure(config, _ROWS)
    assert fig is None


def test_build_figure_table_with_written_answer_returns_none():
    """Returns None for chart_type='table' even when written_answer is set."""
    config = ChartConfig(
        chart_type=ChartType.table, written_answer="Total revenue is $2,500."
    )
    fig = build_figure(config, _SCALAR_ROW)
    assert fig is None


def test_build_figure_empty_rows_returns_none():
    """Returns None when rows list is empty."""
    config = ChartConfig(chart_type=ChartType.bar, x_column="region", y_column="sales")
    fig = build_figure(config, [])
    assert fig is None


def test_build_figure_missing_x_column_returns_none():
    """Returns None when x_column is absent from row dicts."""
    config = ChartConfig(
        chart_type=ChartType.bar, x_column="nonexistent", y_column="sales"
    )
    fig = build_figure(config, _ROWS)
    assert fig is None


def test_build_figure_missing_y_column_returns_none():
    """Returns None when y_column is absent from row dicts."""
    config = ChartConfig(
        chart_type=ChartType.bar, x_column="region", y_column="nonexistent"
    )
    fig = build_figure(config, _ROWS)
    assert fig is None
