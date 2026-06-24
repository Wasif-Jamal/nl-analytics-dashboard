# Proposal: visualisation

## Summary

Implement the **VisualizationAgent** (FR-6, FR-7, FR-8) — a `create_agent()` subagent
that reads `query_result` from `WorkflowState`, selects the clearest presentation for
the result shape, and produces a typed `ChartConfig`. The UI renders the appropriate
Plotly chart, a plain-language LLM-generated sentence for single-value results, or
falls back to the existing dataframe for ambiguous/table-only results. PNG export is
also delivered (FRS §11).

---

## Why

The SQL pipeline and analysis agents (Insight, Follow-Up) are live. The
`VisualizationAgent` is still a stub that returns `{}`, leaving `chart_config` always
`None`. FR-6/7/8 require the system to automatically select and render the right
chart — bar, line, pie, scatter, or table — and to explain single-value results in
plain language. This change replaces the stub with the full `create_agent()` implementation.

---

## Goals

- Replace `VisualizationAgent` stub with a full `create_agent()` instance
- Define a typed `ChartConfig` Pydantic schema (chart_type enum, axis columns, title,
  optional written_answer)
- Implement `VisualizationTools` with a `select_visualization` tool
- Write `VISUALIZATION_SYSTEM_PROMPT` in `app/prompts/visualization_prompt.py`
- Implement `app/utils/chart_helpers.py` — builds Plotly figures from `ChartConfig`
- Update `WorkflowState.chart_config` from `Optional[dict]` to `Optional[ChartConfig]`
- Update `AnalyticsResponse.chart_config` to `Optional[dict]` (serialized from `ChartConfig`)
- Render charts in `website/app.py` (Plotly) with PNG download button
- Render plain-language sentence for single-value (1×1) results via LLM
- Add `kaleido` dependency for PNG export

## Non-Goals

- Custom / user-configurable chart styling beyond automatic type selection
- Multi-series or combined chart types beyond the five specified in FRS §6.3
- Query history panel (separate issue)
- Error handling overhaul (separate issue)

---

## Design

### ChartConfig Schema

New file `app/schemas/chart_config.py`:

```python
class ChartType(str, Enum):
    bar = "bar"
    line = "line"
    pie = "pie"
    scatter = "scatter"
    table = "table"

class ChartConfig(BaseModel):
    chart_type: ChartType
    x_column: Optional[str] = None      # category / time axis
    y_column: Optional[str] = None      # measure axis
    title: str = ""
    written_answer: Optional[str] = None  # set for chart_type="table" 1×1 results
```

- `chart_type="table"` is the explicit fallback for ambiguous results.
- `written_answer` is populated for single-value (1×1) results; the UI renders it
  instead of a chart or metric widget.
- `WorkflowState.chart_config` changes from `Optional[dict]` to `Optional[ChartConfig]`.
- `AnalyticsResponse.chart_config` stays `Optional[dict]` (serialized via `.model_dump()`
  in `ChatService` before the response is built).

### VisualizationAgent

Class in `app/agents/visualization_agent.py`, following the exact pattern of
`InsightAgent` and `FollowupAgent`:

- Constructor injects `llm`, instantiates `VisualizationTools`, calls `create_agent()`
  with `VISUALIZATION_SYSTEM_PROMPT`, `state_schema=VisualizationAgentState`, and
  `name="visualization_agent"`. Stores compiled agent in `self._agent`.
- Private `VisualizationAgentState` — a `MessagesState` subclass with `question`,
  `query_result`, `chart_config`.
- `node(state: WorkflowState) -> dict` bridges outer to inner state: constructs a fresh
  `VisualizationAgentState` (single `HumanMessage` trigger), invokes `self._agent`,
  returns only `{"chart_config": ...}`. The outer `StateGraph` registers
  `visualization_agent.node`, not `_agent` directly.

### VisualizationTools

Class in `app/tools/visualization_tools.py`. Builds one `@tool` closure in `__init__`,
capturing `llm`:

**`select_visualization(tool_call_id, state)`**

- Reads `query_result` and `question` via `Annotated[_VisualizationToolState, InjectedState()]`
  where `_VisualizationToolState` is a `TypedDict(total=False)` with `query_result` and
  `question`. (Same pattern as `InsightTools` and `FollowupTools` — avoids Pydantic
  validation errors caused by running under `VisualizationAgentState`, not `WorkflowState`.)
- Rows are capped at `_MAX_VIZ_ROWS = 10` before serialization.
- When `query_result` is set and rows are non-empty:
  - If `row_count == 1` and `len(columns) == 1` (single-value): makes a nested
    `llm.with_structured_output(ChartConfig)` call instructing the LLM to set
    `chart_type="table"` and populate `written_answer` with a plain-language sentence.
  - Otherwise: makes a nested `llm.with_structured_output(ChartConfig)` call instructing
    the LLM to select the best chart type (bar / line / pie / scatter / table) based on
    result shape.
  - Returns `Command(update={"chart_config": result, "messages": [ToolMessage(...)]})`.
- When `query_result` is `None` or rows empty: returns
  `Command(update={"chart_config": None, "messages": [ToolMessage(content="No data.", ...)]})`.
- On LLM failure: logs exception, returns `Command(update={"chart_config": None, ...})`;
  does NOT set `error_message` (visualization failure is non-fatal).

### VISUALIZATION_SYSTEM_PROMPT

File `app/prompts/visualization_prompt.py`. Directs the agent to call
`select_visualization` once. The nested prompt inside the tool instructs the LLM to:

- Inspect column names, types, and row count
- Select the chart type that best matches the FRS §6.3 mapping table
- For single-value results: write a natural plain-language sentence in `written_answer`
  (e.g. "Total revenue for Q1 2025 is $842,000")
- Always produce a `ChartConfig`; use `chart_type="table"` for ambiguous results

### chart_helpers.py

New file `app/utils/chart_helpers.py`. Pure helper functions (no class):

**`build_figure(chart_config: ChartConfig, rows: list[dict]) -> go.Figure | None`**

- Returns `None` for `chart_type="table"` or when `written_answer` is set.
- Builds and returns the appropriate Plotly figure for bar / line / pie / scatter.
- Uses `plotly.express` where appropriate; falls back to `plotly.graph_objects` for
  scatter.

### Streamlit UI

`website/app.py` — replace the current metric widget path and add chart rendering:

1. **Single-value path** (was `st.metric`): if `chart_config["written_answer"]` is set,
   render `st.info(chart_config["written_answer"])` instead of `st.metric`. No download
   button for this path (consistent with existing CSV rule).
2. **Chart path**: for `chart_type` in `{bar, line, pie, scatter}`, call
   `chart_helpers.build_figure(...)` and render with `st.plotly_chart(fig, use_container_width=True)`.
   Below the chart, render a **Download PNG** button using `fig.to_image(format="png")`.
3. **Table-only path**: `chart_type="table"` and no `written_answer` — render only the
   existing `st.dataframe` (no chart, no PNG button). CSV download button still present.
4. **Fallback** (`chart_config` is `None`): existing behavior — dataframe + CSV download.

The `future-fields-ignored` requirement in the `streamlit-ui` spec is retired:
`chart_config` is now rendered, not ignored.

### WorkflowState & AnalyticsResponse Changes

- `WorkflowState.chart_config`: `Optional[dict]` → `Optional[ChartConfig]`
- `AnalyticsResponse.chart_config`: stays `Optional[dict]`; `ChatService` serializes
  `state["chart_config"].model_dump()` before building the response.

---

## Files Touched

| File | Change |
|---|---|
| `app/schemas/chart_config.py` | **New** — `ChartType` enum + `ChartConfig` model |
| `app/agents/visualization_agent.py` | **Replace stub** — full `create_agent()` implementation |
| `app/tools/visualization_tools.py` | **New** — `VisualizationTools` with `select_visualization` |
| `app/prompts/visualization_prompt.py` | **Update** — fill in `VISUALIZATION_SYSTEM_PROMPT` |
| `app/utils/chart_helpers.py` | **New** — `build_figure()` helper |
| `app/orchestration/state.py` | **Update** — `chart_config: Optional[ChartConfig]` |
| `app/services/chat_service.py` | **Update** — serialize `ChartConfig` → dict for response |
| `website/app.py` | **Update** — chart rendering, written answer, PNG download |
| `pyproject.toml` | **Update** — add `kaleido` dependency |
| `tests/agents/test_visualization_agent.py` | **New** — unit tests |
| `tests/utils/test_chart_helpers.py` | **New** — unit tests for `build_figure` |

---

## Open Questions

None — all design decisions resolved during spec clarification.
