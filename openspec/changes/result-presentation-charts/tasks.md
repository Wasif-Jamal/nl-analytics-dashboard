# Tasks: result-presentation-charts

Source: `proposal.md` + `plan.md`
Spec scenarios mapped one-to-one with pytest tests.

---

## Phase 1 — Schema + Shape Classifier

### 1.1 Create `app/schemas/chart_config.py`
- [ ] Define `ChartConfig(BaseModel)` with fields:
  - `chart_type: Literal["bar", "line", "pie", "scatter", "table", "single_value"]`
  - `x: Optional[str] = None`
  - `y: Optional[str] = None`
  - `title: str`
  - `sentence: Optional[str] = None`
- [ ] Add module docstring (purpose + Pydantic contract)

### 1.2 Create `app/utils/chart_helpers.py`
- [ ] Implement `classify_shape(columns: list[str], dtypes: dict[str, str], row_count: int) -> dict`
- [ ] Heuristics in priority order:
  1. `row_count == 1` and `len(columns) == 1` → `single_value`
  2. 1 string + 1 numeric, col name contains `share`/`percent`/`ratio`/`pct` → `pie`
  3. 1 date/datetime + 1 numeric → `line`
  4. 1 string + 1 numeric → `bar`
  5. exactly 2 numeric columns → `scatter`
  6. else → `table`
- [ ] No Plotly or LLM imports — pure function
- [ ] Add module + function docstring

### 1.3 Update `app/orchestration/state.py`
- [ ] Import `ChartConfig` from `app.schemas.chart_config`
- [ ] Change `chart_config: Optional[dict]` → `chart_config: Optional[ChartConfig]`
- [ ] Update docstring for `chart_config` attribute

### 1.4 Tests — `tests/schemas/test_chart_config.py` (new)
- [ ] `test_bar_config_valid` — bar chart: `x`/`y` set, `sentence=None`
  *(spec: chart-config-schema / bar chart config)*
- [ ] `test_single_value_config` — `chart_type="single_value"`, `x=None`, `y=None`, `sentence` set
  *(spec: chart-config-schema / single_value config)*
- [ ] `test_table_config` — `chart_type="table"`, `x`/`y`/`sentence` all `None`
  *(spec: chart-config-schema / table fallback config)*
- [ ] `test_invalid_chart_type_raises` — invalid `chart_type` string raises `ValidationError`

### 1.5 Tests — `tests/utils/test_chart_helpers.py` (new)
- [ ] `test_single_value` — 1 col, 1 row → `single_value`
  *(spec: chart-helpers-shape-classifier / single value)*
- [ ] `test_bar_category_measure` — string + numeric → `bar`
  *(spec: chart-helpers-shape-classifier / category + measure)*
- [ ] `test_line_time_series` — datetime + numeric → `line`
  *(spec: chart-helpers-shape-classifier / time series)*
- [ ] `test_pie_share_column` — string + numeric with `pct`/`share`/`percent`/`ratio` in name → `pie`
  *(spec: chart-helpers-shape-classifier / parts of whole)*
- [ ] `test_scatter_two_numerics` — two numeric cols → `scatter`
  *(spec: chart-helpers-shape-classifier / two numeric measures)*
- [ ] `test_table_ambiguous` — three mixed cols → `table`
  *(spec: chart-helpers-shape-classifier / ambiguous shape)*

### ✅ Phase 1 Gate
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## Phase 2 — VisualizationTools + VisualizationAgent

### 2.1 Create `app/prompts/visualization_prompt.py`
- [ ] Define `VISUALIZATION_SYSTEM_PROMPT` constant string
- [ ] Prompt must instruct:
  1. Call `analyze_shape` first (no arguments)
  2. If result is `single_value`: call `build_sentence` with a composed sentence and title
  3. Otherwise: call `build_chart_config` with `chart_type`, `x`, `y`, `title`
  4. Never fabricate column names not present in the data
- [ ] Add module docstring

### 2.2 Create `app/tools/visualization_tools.py`
- [ ] Define `VisualizationTools` class with `__init__(self, llm=None)` (llm unused; reserved for future tools)
- [ ] Tool: `analyze_shape`
  - `state: Annotated[WorkflowState, InjectedState]` (auto-injected; LLM passes no args)
  - Reads `state["query_result"]`; builds `dtypes` dict from `df.dtypes`; calls `classify_shape()`
  - Returns `dict` with `chart_type`, `x`, `y`
  - Does NOT write to state (feedback to LLM only)
- [ ] Tool: `build_chart_config`
  - Args: `chart_type: str`, `x: Optional[str]`, `y: Optional[str]`, `title: str`, `tool_call_id: Annotated[str, InjectedToolCallId]`
  - Constructs `ChartConfig`; returns `Command(update={"chart_config": config, "messages": [ToolMessage(...)]})`
- [ ] Tool: `build_sentence`
  - Args: `sentence: str`, `title: str`, `tool_call_id: Annotated[str, InjectedToolCallId]`
  - Constructs `ChartConfig(chart_type="single_value", title=title, sentence=sentence)`; returns `Command`
- [ ] All three stored as instance attributes; add class + method docstrings
- [ ] Import `InjectedState` from `langgraph.prebuilt`

### 2.3 Create `app/agents/visualization_agent.py`
- [ ] Define `VisualizationAgent` class
- [ ] `__init__(self, llm: ChatGoogleGenerativeAI)`:
  - Instantiate `VisualizationTools()`
  - Call `create_agent(model=llm, tools=[...], system_prompt=VISUALIZATION_SYSTEM_PROMPT, state_schema=WorkflowState, name="visualization_agent")`
  - Store as `self._agent`
  - Log initialization
- [ ] Add module + class + `__init__` docstrings

### 2.4 Tests — `tests/agents/test_visualization_agent.py` (new)

*All tools tested via `.func()` attribute — no real LLM or API key needed.*

- [ ] `test_analyze_shape_bar` — inject mock state with 1 string + 1 numeric col → returns `chart_type="bar"`
  *(spec: visualization-agent / bar chart result)*
- [ ] `test_analyze_shape_single_value` — inject mock state with 1 col, 1 row → returns `chart_type="single_value"`
  *(spec: visualization-agent / single value result)*
- [ ] `test_analyze_shape_table_fallback` — inject state with ambiguous cols → returns `chart_type="table"`
  *(spec: visualization-agent / ambiguous → table)*
- [ ] `test_build_chart_config_bar` — call `.func(chart_type="bar", x="cat", y="sales", title="T", tool_call_id="tc1")`; assert `Command.update["chart_config"]` is `ChartConfig` with correct fields
  *(spec: visualization-agent / bar chart result)*
- [ ] `test_build_chart_config_pie` — call with `chart_type="pie"`; assert `x` maps to names column, `y` to values
  *(spec: chart-config-schema / pie mapping)*
- [ ] `test_build_sentence` — call `.func(sentence="Revenue is 1.2M", title="Revenue", tool_call_id="tc2")`; assert `chart_type="single_value"` and `sentence` set
  *(spec: visualization-agent / single value result)*
- [ ] `test_visualization_agent_compiles` — `VisualizationAgent(llm)` constructs `_agent` without error
  *(spec: visualization-prompt / prompt used by agent)*
- [ ] `test_visualization_prompt_not_inline` — assert `VISUALIZATION_SYSTEM_PROMPT` not empty and `visualization_agent.py` source does not contain any inline prompt string
  *(spec: visualization-prompt / no inline prompt strings)*

### ✅ Phase 2 Gate
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## Phase 3 — Graph Wiring + ChatService

### 3.1 Update `app/orchestration/graph.py`
- [ ] Import `VisualizationAgent`
- [ ] Add `route_after_sql(state: WorkflowState) -> str` function:
  - Returns `END` if `state.get("error_message")` is not `None`
  - Returns `"visualization_agent"` otherwise
- [ ] In `build()`:
  - Instantiate `VisualizationAgent(self._llm)`
  - Replace `builder.add_edge("sql_agent", END)` with `builder.add_conditional_edges("sql_agent", route_after_sql)`
  - `builder.add_node("visualization_agent", visualization_agent._agent)`
  - `builder.add_edge("visualization_agent", END)`
- [ ] Update docstring to reflect new graph shape

### 3.2 Update `app/services/chat_service.py`
- [ ] Import `ChartConfig` from `app.schemas.chart_config`
- [ ] After reading `result.get("chart_config")`, serialize it:
  ```python
  chart_config_obj = result.get("chart_config")
  chart_config_dict = chart_config_obj.model_dump() if isinstance(chart_config_obj, ChartConfig) else None
  ```
- [ ] Pass `chart_config=chart_config_dict` to `AnalyticsResponse`
- [ ] Update docstring for `ask()` to mention chart_config serialization

### 3.3 Tests — update `tests/orchestration/test_graph.py`
- [ ] `test_graph_routes_to_visualization_on_success` — mock SQL Agent node returning no `error_message`; assert `visualization_agent` node is reached
  *(spec: visualization-agent-graph-wiring / SQL Agent succeeds)*
- [ ] `test_graph_skips_visualization_on_sql_error` — mock SQL Agent node returning `error_message`; assert `visualization_agent` NOT reached
  *(spec: visualization-agent-graph-wiring / SQL Agent fails)*

### 3.4 Tests — update `tests/services/test_chat_service.py`
- [ ] `test_chart_config_serialized_to_dict` — mock graph returning state with `ChartConfig` object; assert `AnalyticsResponse.chart_config` is a `dict` (result of `.model_dump()`)
  *(spec: response-schema / chart_config in state)*
- [ ] `test_chart_config_none_when_absent` — mock graph returning state without `chart_config`; assert `AnalyticsResponse.chart_config` is `None`
  *(spec: response-schema / chart_config absent)*

### ✅ Phase 3 Gate
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## Phase 4 — Streamlit UI + PNG Export + kaleido

### 4.1 Add kaleido dependency
- [ ] `uv add kaleido` (required for `plotly.io.to_image`)

### 4.2 Update `website/app.py`
- [ ] Add `import plotly.express as px` and `import plotly.io as pio` at top
- [ ] After SQL expander block, read `chart_config = data.get("chart_config")`
- [ ] Implement rendering branches (replace existing `if query_result:` block):

  **`single_value` branch** (when `chart_config["chart_type"] == "single_value"`):
  - `st.metric(label=chart_config["title"], value=chart_config["sentence"])`
  - No dataframe, no CSV button, no PNG button

  **Chart branch** (`bar` / `line` / `pie` / `scatter`):
  - Reconstruct `df = pd.DataFrame(query_result)`
  - Build Plotly figure based on `chart_type`:
    - `bar` → `px.bar(df, x=..., y=..., title=...)`
    - `line` → `px.line(df, x=..., y=..., title=...)`
    - `pie` → `px.pie(df, names=chart_config["x"], values=chart_config["y"], title=...)`
    - `scatter` → `px.scatter(df, x=..., y=..., title=...)`
  - `st.plotly_chart(fig, use_container_width=True)`
  - PNG download button: `st.download_button("Download PNG", data=pio.to_image(fig, format="png"), file_name=f"chart_{timestamp}.png", mime="image/png")`

  **`table` branch** (when `chart_type == "table"` or `chart_config is None`):
  - Existing `st.dataframe` + CSV download button (unchanged)

### 4.3 Tests — update `tests/ui/test_app.py`
- [ ] `test_single_value_renders_metric` — mock response with `chart_config={"chart_type": "single_value", "title": "Revenue", "sentence": "Revenue is 1M", "x": None, "y": None}`; assert `st.metric` called
  *(spec: single-value-rendering)*
- [ ] `test_single_value_no_chart_no_csv_no_png` — same mock; assert `st.plotly_chart`, `st.download_button` with CSV, and PNG download button NOT called
  *(spec: single-value-rendering / no chart or buttons)*
- [ ] `test_bar_chart_renders_plotly` — mock response with `chart_type="bar"`; assert `st.plotly_chart` called
  *(spec: chart-rendering / bar chart rendered)*
- [ ] `test_pie_chart_uses_names_values` — mock response with `chart_type="pie"`, `x="category"`, `y="sales"`; assert `px.pie` called with `names="category"` and `values="sales"`
  *(spec: chart-rendering / pie chart rendered)*
- [ ] `test_line_chart_renders` — mock response with `chart_type="line"`; assert `px.line` called
  *(spec: chart-rendering)*
- [ ] `test_scatter_chart_renders` — mock response with `chart_type="scatter"`; assert `px.scatter` called
  *(spec: chart-rendering)*
- [ ] `test_png_download_button_visible_for_chart` — mock bar chart response; assert `st.download_button` called with `mime="image/png"`
  *(spec: png-export / PNG button visible)*
- [ ] `test_png_button_absent_for_single_value` — mock single_value response; assert no PNG `st.download_button`
  *(spec: png-export / PNG button absent for metric)*
- [ ] `test_png_button_absent_for_table` — mock `chart_type="table"` response; assert no PNG `st.download_button`
  *(spec: png-export / PNG button absent for table)*
- [ ] `test_table_fallback_renders_dataframe` — mock `chart_type="table"` response; assert `st.dataframe` called and CSV download button present
  *(spec: table-fallback-rendering)*

### ✅ Phase 4 Gate
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## Summary

| Phase | New Files | Modified Files | Tests |
|---|---|---|---|
| 1 | `chart_config.py`, `chart_helpers.py` | `state.py` | 10 |
| 2 | `visualization_prompt.py`, `visualization_tools.py`, `visualization_agent.py` | — | 8 |
| 3 | — | `graph.py`, `chat_service.py` | 4 |
| 4 | — | `website/app.py` (+ `uv add kaleido`) | 10 |
| **Total** | **5 new** | **4 modified** | **32 tests** |
