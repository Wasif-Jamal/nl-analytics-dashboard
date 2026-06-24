# Spec Delta: visualisation-pipeline (visualisation change)

## Delta Summary

Introduces the full `VisualizationAgent` (replacing the stub), `VisualizationTools`,
`ChartConfig` schema, `chart_helpers`, and PNG export support. All requirements in this
file are new additions to the system.

---

## ADDED Requirements

### Requirement: chart-config-schema

`ChartConfig` in `app/schemas/chart_config.py` SHALL be a Pydantic `BaseModel` with a
`ChartType` string enum. It is used as both the `with_structured_output` target inside
`select_visualization` and the typed field in `WorkflowState`.

```
ChartType (str, Enum): bar | line | pie | scatter | table

ChartConfig (BaseModel):
  chart_type: ChartType
  x_column: Optional[str] = None     # category / time axis
  y_column: Optional[str] = None     # measure axis
  title: str = ""
  written_answer: Optional[str] = None  # plain-language sentence for single-value results
```

`WorkflowState.chart_config` SHALL be updated from `Optional[dict]` to
`Optional[ChartConfig]`. `AnalyticsResponse.chart_config` SHALL remain `Optional[dict]`;
`ChatService` SHALL serialize `ChartConfig` via `.model_dump()` before building the
response.

#### Scenario: ChartConfig validated by Pydantic
- **WHEN** the LLM returns a response for `with_structured_output(ChartConfig)`
- **THEN** Pydantic validates `chart_type` is a valid `ChartType` enum member; if
  validation fails, LangChain retries automatically

#### Scenario: table fallback is always valid
- **WHEN** the LLM sets `chart_type="table"` and omits `x_column` / `y_column`
- **THEN** the model is valid; `chart_helpers.build_figure` returns `None` for this type

---

### Requirement: visualization-agent

`VisualizationAgent` in `app/agents/visualization_agent.py` SHALL replace the existing
stub and become a full `create_agent()` instance. Its compiled agent SHALL be exposed
via `self._agent` and use a private `VisualizationAgentState` (a `MessagesState`
subclass with `question`, `query_result`, `chart_config`). The agent SHALL use
`VISUALIZATION_SYSTEM_PROMPT` from `app/prompts/visualization_prompt.py` and
`state_schema=VisualizationAgentState`. A `node(state: WorkflowState) -> dict` method
SHALL bridge the outer state to the inner state: it constructs a fresh
`VisualizationAgentState` (with a single `HumanMessage` trigger) so the model starts
with a clean context, invokes `self._agent`, and returns only `{"chart_config": ...}`.
The outer `StateGraph` registers `visualization_agent.node` (a function node), NOT
`visualization_agent._agent` directly.

#### Scenario: supervisor routes to VisualizationAgent
- **WHEN** the outer graph routes to `"visualization_agent"` after a successful SQL Agent run
- **THEN** `VisualizationAgent.node()` is called; it invokes `_agent` with a fresh
  `VisualizationAgentState`; the model sees only a single HumanMessage (not the prior SQL
  conversation); `select_visualization` is invisible to the outer graph

#### Scenario: agent calls select_visualization once
- **WHEN** `VisualizationAgent.node()` is called with a non-empty `query_result` in `WorkflowState`
- **THEN** the LLM calls `select_visualization` exactly once; `node()` propagates only
  `chart_config` back to `WorkflowState`

---

### Requirement: visualization-tools

`VisualizationTools` in `app/tools/visualization_tools.py` SHALL build one `@tool`
closure (`select_visualization`) in `__init__`, capturing `llm`. The tool SHALL be
stored as `self.select_visualization` and passed directly to `create_agent`.

`select_visualization` tool contract:

- Reads `query_result` and `question` via `Annotated[_VisualizationToolState, InjectedState()]`
  where `_VisualizationToolState` is a `TypedDict(total=False)` declaring only those two
  fields. The LLM does not pass rows as arguments.
- Rows are capped at `_MAX_VIZ_ROWS = 10` before JSON serialization; excess rows are
  dropped and a warning is logged.
- When `query_result` is set and `rows` is non-empty:
  - Makes a nested `llm.with_structured_output(ChartConfig)` call passing the original
    question, column names, row count, and up to 10 rows serialized as JSON.
  - For single-value results (`row_count == 1` and `len(columns) == 1`): the nested
    prompt instructs the LLM to set `chart_type="table"` and populate `written_answer`
    with a natural-language sentence (e.g. "Total revenue for Q1 2025 is $842,000").
  - For all other shapes: the nested prompt instructs the LLM to select the best
    chart type per the FRS §6.3 mapping (bar / line / pie / scatter / table).
  - Returns `Command(update={"chart_config": result, "messages": [ToolMessage(...)]})`.
- When `query_result` is `None` or `rows` is empty: returns
  `Command(update={"chart_config": None, "messages": [ToolMessage(content="No data.", ...)]})`.
- On LLM failure: logs exception, returns `Command(update={"chart_config": None, ...})`;
  does NOT set `error_message` (visualization failure is non-fatal).

#### Scenario: multi-row result — chart type selected
- **WHEN** `select_visualization` is called and `query_result` has multiple rows and columns
- **THEN** the nested LLM call returns a `ChartConfig` with a non-table `chart_type` and
  populated `x_column` / `y_column`; `WorkflowState.chart_config` is set; `error_message`
  is unchanged

#### Scenario: single-value result — written answer produced
- **WHEN** `select_visualization` is called and `query_result` has exactly 1 row and 1 column
- **THEN** the nested LLM call returns a `ChartConfig` with `chart_type="table"` and
  `written_answer` set to a plain-language sentence; `error_message` is unchanged

#### Scenario: ambiguous result — table fallback
- **WHEN** `select_visualization` is called and the result shape does not match any
  specific chart type
- **THEN** the LLM returns `chart_type="table"` with `written_answer=None`

#### Scenario: query_result absent — no LLM call
- **WHEN** `select_visualization` is called and `state["query_result"]` is `None`
- **THEN** `WorkflowState.chart_config` is set to `None`; no LLM call is made;
  `error_message` is unchanged

#### Scenario: LLM call fails — non-fatal
- **WHEN** the nested `with_structured_output` call raises an exception
- **THEN** `WorkflowState.chart_config` is set to `None`; the error is logged
  server-side; `error_message` is NOT set

#### Scenario: rows truncated at 10
- **WHEN** `select_visualization` is called and `query_result.rows` has more than 10 rows
- **THEN** only the first 10 rows are serialized; a warning is logged; the LLM call
  proceeds normally

---

### Requirement: visualization-prompt

`VISUALIZATION_SYSTEM_PROMPT` in `app/prompts/visualization_prompt.py` SHALL be a
non-empty string constant that directs the agent to call `select_visualization` exactly
once. The prompt text SHALL instruct the agent that its sole job is to call the tool —
no analysis or commentary is needed.

An inner prompt (`VISUALIZATION_INNER_PROMPT`) SHALL be defined in the same file and
used inside the `select_visualization` tool for the nested `with_structured_output` LLM
call. It SHALL include the FRS §6.3 mapping table (result shape → chart type) and
instructions for the single-value written-answer format.

#### Scenario: prompt is non-empty
- **WHEN** `app/prompts/visualization_prompt.py` is imported
- **THEN** `VISUALIZATION_SYSTEM_PROMPT` is a non-empty string; `VISUALIZATION_INNER_PROMPT`
  is a non-empty string

---

### Requirement: chart-helpers

`app/utils/chart_helpers.py` SHALL define a module-level `build_figure` function (no
class) that builds a Plotly figure from a `ChartConfig` and a list of rows.

**`build_figure(chart_config: ChartConfig, rows: list[dict]) -> go.Figure | None`**

- Returns `None` when `chart_config.chart_type == ChartType.table`.
- For `bar`: returns a `plotly.express.bar` figure using `x=chart_config.x_column`,
  `y=chart_config.y_column`, `title=chart_config.title`.
- For `line`: returns a `plotly.express.line` figure.
- For `pie`: returns a `plotly.express.pie` figure with `names=x_column`,
  `values=y_column`.
- For `scatter`: returns a `plotly.express.scatter` figure.
- If `rows` is empty or either required column is missing from the data: returns `None`.

#### Scenario: bar chart built
- **WHEN** `build_figure` receives `chart_type="bar"` and non-empty rows with the
  named columns present
- **THEN** a Plotly Figure object is returned; no exception is raised

#### Scenario: table type returns None
- **WHEN** `build_figure` receives `chart_type="table"`
- **THEN** `None` is returned regardless of row contents

#### Scenario: missing column returns None
- **WHEN** `build_figure` receives a chart type requiring `x_column` but `x_column` is
  absent from the row dicts
- **THEN** `None` is returned; no exception propagates to the caller

#### Scenario: empty rows returns None
- **WHEN** `build_figure` is called with an empty `rows` list
- **THEN** `None` is returned regardless of chart type

---

### Requirement: png-export

The `kaleido` package SHALL be added as a production dependency (required at runtime for
`fig.to_image(format="png")`). The Streamlit UI SHALL render a **Download PNG** button
below every rendered chart (bar, line, pie, scatter). No PNG button appears for the
table-only or written-answer paths.

#### Scenario: PNG download button present for charts
- **WHEN** `chart_config.chart_type` is one of `{bar, line, pie, scatter}` and a
  Plotly figure is rendered
- **THEN** a `st.download_button` labelled "Download PNG" appears below the chart;
  clicking it downloads `chart_<timestamp>.png` as `image/png` bytes via
  `fig.to_image(format="png")`

#### Scenario: PNG button absent for table and written-answer paths
- **WHEN** `chart_config.chart_type == "table"` (with or without `written_answer`)
  or `chart_config` is `None`
- **THEN** no PNG download button is rendered
