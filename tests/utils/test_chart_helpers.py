"""Tests for app.utils.chart_helpers.classify_shape."""

from app.utils.chart_helpers import classify_shape


def test_single_value():
    """1 column, 1 row → single_value with x and y None."""
    result = classify_shape(["total_sales"], {"total_sales": "float64"}, row_count=1)
    assert result["chart_type"] == "single_value"
    assert result["x"] is None
    assert result["y"] is None


def test_bar_category_measure():
    """1 object col + 1 float64 col, 5 rows → bar chart."""
    result = classify_shape(
        ["category", "sales"],
        {"category": "object", "sales": "float64"},
        row_count=5,
    )
    assert result["chart_type"] == "bar"
    assert result["x"] == "category"
    assert result["y"] == "sales"


def test_line_time_series():
    """1 datetime64[ns] col + 1 float64 col, 12 rows → line chart."""
    result = classify_shape(
        ["order_date", "sales"],
        {"order_date": "datetime64[ns]", "sales": "float64"},
        row_count=12,
    )
    assert result["chart_type"] == "line"
    assert result["x"] == "order_date"
    assert result["y"] == "sales"


def test_pie_share_column():
    """1 object col + 1 numeric col with 'pct' in the name → pie chart."""
    result = classify_shape(
        ["segment", "revenue_pct"],
        {"segment": "object", "revenue_pct": "float64"},
        row_count=3,
    )
    assert result["chart_type"] == "pie"
    assert result["x"] == "segment"
    assert result["y"] == "revenue_pct"


def test_scatter_two_numerics():
    """2 float64 columns → scatter chart."""
    result = classify_shape(
        ["revenue", "profit"],
        {"revenue": "float64", "profit": "float64"},
        row_count=10,
    )
    assert result["chart_type"] == "scatter"
    assert result["x"] == "revenue"
    assert result["y"] == "profit"


def test_table_ambiguous():
    """3 columns (1 object + 2 float64) → table fallback."""
    result = classify_shape(
        ["a", "b", "c"],
        {"a": "object", "b": "float64", "c": "float64"},
        row_count=5,
    )
    assert result["chart_type"] == "table"
    assert result["x"] is None
    assert result["y"] is None
