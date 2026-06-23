"""Tests for app.schemas.chart_config (ChartConfig Pydantic contract)."""

import pytest
from pydantic import ValidationError

from app.schemas.chart_config import ChartConfig


def test_bar_config_valid():
    """ChartConfig for a bar chart sets x, y, title and leaves sentence None."""
    config = ChartConfig(chart_type="bar", x="category", y="sales", title="T")
    assert config.chart_type == "bar"
    assert config.x == "category"
    assert config.y == "sales"
    assert config.title == "T"
    assert config.sentence is None


def test_single_value_config():
    """ChartConfig for single_value carries a sentence; x and y are None."""
    config = ChartConfig(
        chart_type="single_value",
        title="Revenue",
        sentence="Revenue is 1M",
    )
    assert config.chart_type == "single_value"
    assert config.sentence == "Revenue is 1M"
    assert config.x is None
    assert config.y is None


def test_table_config():
    """ChartConfig for table leaves x, y, and sentence all None."""
    config = ChartConfig(chart_type="table", title="All Orders")
    assert config.chart_type == "table"
    assert config.x is None
    assert config.y is None
    assert config.sentence is None


def test_invalid_chart_type_raises():
    """An unsupported chart_type string raises a Pydantic ValidationError."""
    with pytest.raises(ValidationError):
        ChartConfig(chart_type="heatmap", title="Bad Type")
