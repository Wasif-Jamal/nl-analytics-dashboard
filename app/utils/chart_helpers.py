"""Pure helpers for chart type classification.

``classify_shape`` inspects a query result's column names, pandas dtype strings,
and row count and returns a dict describing the best chart type for that shape.
It contains no Plotly, LangChain, or LLM imports — it is a deterministic
classification function used by the Visualization Agent before it builds a
``ChartConfig``.
"""

_PIE_KEYWORDS = frozenset({"share", "percent", "ratio", "pct"})


def classify_shape(
    columns: list[str], dtypes: dict[str, str], row_count: int
) -> dict[str, str | None]:
    """Classify the best chart type for a query result by inspecting its shape.

    Applies heuristics in priority order:

    1. Single cell (1 column, 1 row) → single_value
    2. 1 string + 1 numeric col whose name contains share/percent/ratio/pct → pie
    3. 1 date/datetime + 1 numeric col → line
    4. 1 string + 1 numeric col → bar
    5. Exactly 2 numeric columns → scatter
    6. All other shapes → table

    Dtype classification rules (based on pandas dtype name strings):
    - String/categorical: dtype == ``"object"`` or starts with ``"string"``
    - Numeric: starts with ``"float"``, ``"int"``, or ``"uint"``
    - Date/datetime: starts with ``"datetime"`` or dtype == ``"date"``

    Args:
        columns: Ordered list of column names in the query result.
        dtypes: Mapping of column name to pandas dtype name string
            (e.g. ``"object"``, ``"float64"``, ``"datetime64[ns]"``).
        row_count: Number of rows returned by the query.

    Returns:
        A dict with keys ``chart_type``, ``x``, and ``y``.  ``x`` and ``y``
        are either a column-name string or ``None``.
    """

    def _is_string(col: str) -> bool:
        dtype = dtypes.get(col, "")
        return dtype == "object" or dtype.startswith("string")

    def _is_numeric(col: str) -> bool:
        dtype = dtypes.get(col, "")
        return (
            dtype.startswith("float")
            or dtype.startswith("int")
            or dtype.startswith("uint")
        )

    def _is_date(col: str) -> bool:
        dtype = dtypes.get(col, "")
        return dtype.startswith("datetime") or dtype == "date"

    # 1. Single cell
    if row_count == 1 and len(columns) == 1:
        return {"chart_type": "single_value", "x": None, "y": None}

    string_cols = [c for c in columns if _is_string(c)]
    numeric_cols = [c for c in columns if _is_numeric(c)]
    date_cols = [c for c in columns if _is_date(c)]

    # 2. Pie — 1 string + 1 numeric with a share-like column name
    if len(string_cols) == 1 and len(numeric_cols) == 1:
        numeric_col = numeric_cols[0]
        if any(kw in numeric_col.lower() for kw in _PIE_KEYWORDS):
            return {
                "chart_type": "pie",
                "x": string_cols[0],
                "y": numeric_col,
            }

    # 3. Line — 1 date + 1 numeric
    if len(date_cols) == 1 and len(numeric_cols) == 1:
        return {
            "chart_type": "line",
            "x": date_cols[0],
            "y": numeric_cols[0],
        }

    # 4. Bar — 1 string + 1 numeric
    if len(string_cols) == 1 and len(numeric_cols) == 1:
        return {
            "chart_type": "bar",
            "x": string_cols[0],
            "y": numeric_cols[0],
        }

    # 5. Scatter — exactly 2 numeric columns
    if len(columns) == 2 and len(numeric_cols) == 2:
        return {"chart_type": "scatter", "x": columns[0], "y": columns[1]}

    # 6. Fallback
    return {"chart_type": "table", "x": None, "y": None}
