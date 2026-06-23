# Spec: visualization-agent

## ADDED Requirements

### Requirement: chart-config-schema

`ChartConfig` SHALL be defined in `app/schemas/chart_config.py` as a Pydantic `BaseModel` with the following fields:

| Field | Type | Notes |
|---|---|---|
| `chart_type` | `Literal["bar", "line", "pie", "scatter", "table", "single_value"]` | Required |
| `x` | `Optional[str]` | x-axis column name (bar/line/scatter) or names column (pie). `None` for `single_value` and `table`. |
| `y` | `Optional[str]` | y-axis column name (bar/line/scatter) or values column (pie). `None` for `single_value` and `table`. |
| `title` | `str` | Chart or metric title |
| `sentence` | `Optional[str]` | Plain-language sentence; set only when `chart_type == "single_value"`. `None` for all other types. |

#### Scenario: bar chart config
- **WHEN** a `ChartConfig` is constructed with `chart_type="bar"`, `x="category"`, `y="sales"`, `title="Sales by Category"`
- **THEN** `chart_type`, `x`, `y`, and `title` are set; `sentence` is `None`

#### Scenario: single_value config
- **WHEN** a `ChartConfig` is constructed with `chart_type="single_value"`, `title="Total Revenue"`, `sentence="Total revenue for this quarter is 200K USD"`
- **THEN** `x` and `y` are `None`; `sentence` holds the plain-language string

#### Scenario: table fallback config
- **WHEN** a `ChartConfig` is constructed with `chart_type="table"`
- **THEN** `x`, `y`, and `sentence` are all `None`

---

### Requirement: chart-helpers-shape-classifier

`app/utils/chart_helpers.py` SHALL expose a `classify_shape(columns: list[str], dtypes: dict[str, str], row_count: int) -> dict` function that returns `chart_type` and suggested `x`/`y` column names based on the following heuristics (evaluated in priority order):

| Priority | Rule | Result |
|---|---|---|
| 1 | `row_count == 1` and `len(columns) == 1` | `single_value` |
| 2 | 1 string + 1 numeric col; col name contains `share`/`percent`/`ratio`/`pct` | `pie` |
| 3 | 1 date/datetime + 1 numeric col | `line` |
| 4 | 1 string + 1 numeric col | `bar` |
| 5 | Exactly 2 numeric cols | `scatter` |
| 6 | All other shapes | `table` |

`classify_shape` has no Plotly or LLM dependency — it is a pure function.

#### Scenario: category + measure → bar
- **WHEN** `columns=["category", "sales"]`, dtypes indicate `category` is string and `sales` is numeric, `row_count > 1`
- **THEN** `classify_shape` returns `{"chart_type": "bar", "x": "category", "y": "sales"}`

#### Scenario: single value → single_value
- **WHEN** `columns=["total_revenue"]`, `row_count == 1`
- **THEN** `classify_shape` returns `{"chart_type": "single_value", "x": None, "y": None}`

#### Scenario: date + numeric → line
- **WHEN** `columns=["order_date", "sales"]`, dtype of `order_date` is datetime, `row_count > 1`
- **THEN** `classify_shape` returns `{"chart_type": "line", "x": "order_date", "y": "sales"}`

#### Scenario: two numeric columns → scatter
- **WHEN** `columns=["revenue", "profit"]`, both numeric, `row_count > 1`
- **THEN** `classify_shape` returns `{"chart_type": "scatter", "x": "revenue", "y": "profit"}`

#### Scenario: ambiguous shape → table
- **WHEN** the shape matches no heuristic (e.g. three or more mixed columns)
- **THEN** `classify_shape` returns `{"chart_type": "table", "x": None, "y": None}`

---

### Requirement: visualization-agent

`VisualizationAgent` SHALL be defined in `app/agents/visualization_agent.py` as a class that builds a `create_agent()` instance in `__init__`. It SHALL have three `@tool`-decorated internal tools provided via a companion `VisualizationTools` class in `app/tools/visualization_tools.py`:

| Tool | Responsibility |
|---|---|
| `analyze_shape` | Reads `query_result` from injected `WorkflowState` via `InjectedState`; calls `classify_shape()`; returns `chart_type`, `x`, `y` as a dict |
| `build_chart_config` | Takes `chart_type`, `x`, `y`, `title`; constructs `ChartConfig` and writes to `WorkflowState` via `Command` |
| `build_sentence` | Takes LLM-composed `sentence` and `title`; writes `ChartConfig(chart_type="single_value", ...)` to `WorkflowState` via `Command` |

The agent's LLM drives the tool-calling loop. For `single_value`, it calls `analyze_shape` → `build_sentence`. For all other types, it calls `analyze_shape` → `build_chart_config`. Internal tools are invisible to the supervisor. The compiled agent is stored as `self._agent`.

#### Scenario: bar chart result
- **WHEN** `VisualizationAgent` is invoked with `query_result` containing category + sales columns
- **THEN** the agent calls `analyze_shape` → `build_chart_config`; `WorkflowState.chart_config` is a `ChartConfig` with `chart_type="bar"` and correct `x`/`y`

#### Scenario: single value result
- **WHEN** `VisualizationAgent` is invoked with a 1×1 `query_result`
- **THEN** the agent calls `analyze_shape` → `build_sentence`; `WorkflowState.chart_config` is a `ChartConfig` with `chart_type="single_value"` and a non-empty `sentence`

#### Scenario: ambiguous shape → table fallback
- **WHEN** `analyze_shape` returns `chart_type="table"`
- **THEN** `build_chart_config` is called with `chart_type="table"`; `x`, `y`, and `sentence` are `None`

---

### Requirement: visualization-prompt

`app/prompts/visualization_prompt.py` SHALL define a `VISUALIZATION_SYSTEM_PROMPT` constant. The prompt SHALL instruct the agent to call `analyze_shape` first, then either `build_sentence` (single_value) or `build_chart_config` (all other types). It SHALL never fabricate column names not present in the data. Prompt text is never hardcoded in `visualization_agent.py`.

#### Scenario: prompt is used by the agent
- **WHEN** `VisualizationAgent.__init__` builds the `create_agent()` instance
- **THEN** `VISUALIZATION_SYSTEM_PROMPT` is passed as `system_prompt` to `create_agent()`; no prompt string literal appears inside the agent class

---

### Requirement: visualization-agent-graph-wiring

`AnalyticsGraph` (`app/orchestration/graph.py`) SHALL be updated to add a `visualization_agent` subgraph node. A `route_after_sql` conditional edge function SHALL route to `"visualization_agent"` when `error_message` is `None`, and to `END` when `error_message` is set. The updated graph flow is `START → sql_agent → [route_after_sql] → visualization_agent → END` (success) or `START → sql_agent → END` (error).

#### Scenario: SQL Agent succeeds
- **WHEN** the SQL Agent completes with `error_message=None`
- **THEN** `route_after_sql` returns `"visualization_agent"`; `chart_config` is set in state before the graph exits

#### Scenario: SQL Agent fails
- **WHEN** the SQL Agent sets `error_message` in state
- **THEN** `route_after_sql` returns `END`; `visualization_agent` is NOT invoked; `chart_config` remains `None`
