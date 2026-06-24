"""Chart building utilities for the Natural Language Analytics Dashboard.

``build_figure`` converts a ``ChartConfig`` and raw query rows into a Plotly
figure. Returns ``None`` for the table-only path (including single-value
written-answer results), when required columns are missing, or when rows are
empty. No exception propagates to callers — all failures surface as ``None``.
"""

from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from app.config.log_config import config as log_config
from app.schemas.chart_config import ChartConfig, ChartType

logger = log_config.get_logger(__name__)


def build_figure(chart_config: ChartConfig, rows: list[dict]) -> Optional[go.Figure]:
    """Build a Plotly figure from a ChartConfig and query rows.

    Dispatches to the appropriate ``plotly.express`` function based on
    ``chart_config.chart_type``. Returns ``None`` for the table-only path,
    empty rows, or missing columns. No exception propagates to the caller.

    Args:
        chart_config: Visualization configuration produced by the
            ``VisualizationAgent``.
        rows: Query result rows as ``list[dict]`` (column → value per row).

    Returns:
        A Plotly ``Figure`` object, or ``None`` if no chart can be built.
    """
    if chart_config.chart_type == ChartType.table:
        return None

    if not rows:
        logger.debug("build_figure: empty rows, returning None")
        return None

    x_col = chart_config.x_column
    y_col = chart_config.y_column
    title = chart_config.title

    if x_col and x_col not in rows[0]:
        logger.warning("build_figure: x_column '%s' not found in rows", x_col)
        return None
    if y_col and y_col not in rows[0]:
        logger.warning("build_figure: y_column '%s' not found in rows", y_col)
        return None

    try:
        df = pd.DataFrame(rows)
        if chart_config.chart_type == ChartType.bar:
            return px.bar(df, x=x_col, y=y_col, title=title)
        if chart_config.chart_type == ChartType.line:
            return px.line(df, x=x_col, y=y_col, title=title)
        if chart_config.chart_type == ChartType.pie:
            return px.pie(df, names=x_col, values=y_col, title=title)
        if chart_config.chart_type == ChartType.scatter:
            return px.scatter(df, x=x_col, y=y_col, title=title)
    except Exception as exc:  # noqa: BLE001
        logger.warning("build_figure: failed to build figure: %s", exc)
        return None

    return None
