# Tasks: visualisation

Implements FR-6, FR-7, FR-8. Replaces the `VisualizationAgent` stub with a full
`create_agent()` instance, introduces `ChartConfig`, builds Plotly rendering in the UI,
and adds PNG export. Graph wiring (`graph.py`) is unchanged.

---

## Phase 1 — Schema & Utils

- [ ] **1.1** Create `app/schemas/chart_config.py` with `ChartType` (str enum: `bar | line | pie | scatter | table`) and `ChartConfig` (BaseModel: `chart_type`, `x_column`, `y_column`, `title`, `written_answer`)
- [ ] **1.2** Create `app/utils/chart_helpers.py` with `build_figure(chart_config: ChartConfig, rows: list[dict]) -> go.Figure | None` — dispatch bar/line/pie/scatter via `plotly.express`; return `None` for `chart_type="table"`, empty rows, or missing column

**Checkpoint 1:**
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## Phase 2 — State & ChatService

- [ ] **2.1** Update `app/orchestration/state.py`: import `ChartConfig`; change `chart_config` field from `Optional[dict]` to `Optional[ChartConfig]`
- [ ] **2.2** Update `app/services/chat_service.py` `ask()`: serialize `chart_config_obj.model_dump()` → `chart_config` dict before building `AnalyticsResponse` (was a direct pass-through)

**Checkpoint 2:**
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## Phase 3 — Agent

- [ ] **3.1** Update `app/prompts/visualization_prompt.py`: write `VISUALIZATION_SYSTEM_PROMPT` (instructs LLM to call `select_visualization` once and stop) and `VISUALIZATION_INNER_PROMPT` (includes FRS §6.3 shape→chart-type mapping; single-value instruction to set `chart_type="table"` and populate `written_answer`; cap at 10 rows)
- [ ] **3.2** Create `app/tools/visualization_tools.py` with `VisualizationTools` class:
  - `_VisualizationToolState` TypedDict (total=False): `question`, `query_result`
  - `_MAX_VIZ_ROWS = 10`
  - `select_visualization` `@tool` closure capturing `llm`: reads injected state; returns `Command(chart_config=None)` on empty/missing data; caps rows at 10 (warn if truncated); calls `llm.with_structured_output(ChartConfig).invoke(...)`; returns `Command(chart_config=result)`; on exception logs warning and returns `Command(chart_config=None)` without setting `error_message`
- [ ] **3.3** Replace `app/agents/visualization_agent.py` stub with full implementation:
  - `VisualizationAgentState(MessagesState)`: `question`, `query_result`, `chart_config`
  - `VisualizationAgent.__init__`: instantiates `VisualizationTools`, calls `create_agent()` with `VISUALIZATION_SYSTEM_PROMPT`, `state_schema=VisualizationAgentState`, `name="visualization_agent"`
  - `node(state: WorkflowState) -> dict`: constructs fresh `VisualizationAgentState` with single `HumanMessage`, invokes `self._agent`, returns `{"chart_config": result.get("chart_config")}`
- [ ] **3.4** Add `kaleido` dependency: `uv add kaleido`

**Checkpoint 3:**
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## Phase 4 — Streamlit UI

- [ ] **4.1** Update `website/app.py` — replace the `st.metric` single-value block and add chart rendering after the SQL expander:
  - Read `chart_config = data.get("chart_config")` (dict or None)
  - **Written-answer path** (`chart_config["written_answer"]` set): `st.info(written_answer)` — no dataframe, no CSV, no PNG button
  - **Chart path** (`chart_type` in `{bar, line, pie, scatter}`): reconstruct `ChartConfig(**chart_config)`, call `build_figure(config_obj, query_result)`; if figure non-None: `st.plotly_chart(fig, use_container_width=True)` + `st.download_button("Download PNG", fig.to_image(format="png"), f"chart_{timestamp}.png", "image/png")`; if figure is None: fall through to dataframe
  - **Table-only path** (`chart_type == "table"`, no `written_answer`): show existing dataframe + CSV button
  - **Fallback** (`chart_config` is None): existing dataframe + CSV button unchanged

**Checkpoint 4:**
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## Phase 5 — Tests

All tests mock LLM calls; no real API key or network needed. Call tool functions via `.func()` directly to bypass LangChain wrapper.

- [ ] **5.1** Create `tests/utils/test_chart_helpers.py`:
  - `test_build_figure_bar` — returns `go.Figure` for `chart_type="bar"` with valid rows
  - `test_build_figure_line` — returns `go.Figure` for `chart_type="line"`
  - `test_build_figure_pie` — returns `go.Figure` for `chart_type="pie"`
  - `test_build_figure_scatter` — returns `go.Figure` for `chart_type="scatter"`
  - `test_build_figure_table_returns_none` — returns `None` for `chart_type="table"`
  - `test_build_figure_missing_column_returns_none` — returns `None` when `x_column` absent from row dicts
  - `test_build_figure_empty_rows_returns_none` — returns `None` when `rows=[]`

- [ ] **5.2** Create `tests/agents/test_visualization_agent.py`:
  - `test_select_visualization_success` — multi-row → LLM called → `chart_config` set with a chart type
  - `test_select_visualization_single_value` — 1×1 result → LLM called → `chart_type="table"`, `written_answer` set
  - `test_select_visualization_empty_rows` — `rows=[]` → no LLM call → `chart_config=None`
  - `test_select_visualization_no_query_result` — `query_result=None` → no LLM call → `chart_config=None`
  - `test_select_visualization_llm_failure` — LLM raises → `chart_config=None`, `error_message` NOT in `command.update`
  - `test_select_visualization_rows_truncated` — 15 rows supplied → only first 10 serialized in the prompt (assert via `mock_chain.invoke` call arg)
  - `test_visualization_agent_compiles` — `VisualizationAgent(mock_llm)._agent` is `CompiledStateGraph`

**Checkpoint 5 (final):**
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## Commit Plan

| Commit | Phases | Message |
|---|---|---|
| After checkpoint 1 | 1 | `feat(visualisation): add ChartConfig schema and chart_helpers` |
| After checkpoint 2 | 2 | `feat(visualisation): wire ChartConfig into WorkflowState and ChatService` |
| After checkpoint 3 | 3+3.4 | `feat(visualisation): implement VisualizationAgent with select_visualization tool` |
| After checkpoint 4 | 4 | `feat(visualisation): render charts and written answers in Streamlit UI` |
| After checkpoint 5 | 5 | `test(visualisation): add visualization agent and chart_helpers tests` |
