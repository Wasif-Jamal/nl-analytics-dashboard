# Plan: result-presentation-charts

Source: `openspec/changes/result-presentation-charts/proposal.md` + `spec.md`
Requirements: FRS §6.3, §11 — FR-6, FR-7, FR-8

---

## Current State

- `WorkflowState.chart_config` exists but is typed `Optional[dict]` — placeholder.
- `AnalyticsResponse.chart_config` exists as `Optional[dict]` — already forwarded by `ChatService.ask()`.
- Graph is `START → sql_agent → END`; no visualization node.
- `website/app.py` renders `st.metric` for 1×1 results and `st.dataframe` + CSV for multi-row. No chart rendering, no PNG export.
- `app/utils/chart_helpers.py`, `app/agents/visualization_agent.py`, `app/tools/visualization_tools.py`, `app/prompts/visualization_prompt.py` do not exist.
- `app/schemas/chart_config.py` does not exist.

---

## Architecture Decisions

### ChartConfig lives in `app/schemas/chart_config.py`
Matches the established schema convention (`sql_result.py` → `chart_config.py`). `WorkflowState.chart_config` is updated from `Optional[dict]` to `Optional[ChartConfig]`; `AnalyticsResponse.chart_config` stays `Optional[dict]` (JSON-safe, serialized by ChatService via `.model_dump()`).

### VisualizationTools follows the SqlTools pattern
A companion `VisualizationTools` class in `app/tools/visualization_tools.py` builds three `@tool` closures in `__init__`. `VisualizationAgent` instantiates it and passes the tools to `create_agent()`. Mirrors `SqlTools` / `SqlAgent` exactly.

### `analyze_shape` uses `InjectedState` to read `query_result`
The tool needs the DataFrame's dtypes to classify shape. Passing dtypes through the LLM would be fragile. `InjectedState` injects `WorkflowState` directly — same injection mechanism as `InjectedToolCallId` already used in `execute_sql`. The LLM calls `analyze_shape()` with no arguments.

### `build_sentence` receives the composed sentence as an argument
The agent's LLM generates the natural-language sentence text ("Total revenue for Q1 is 1.2M USD") and passes it as a `sentence: str` argument. `build_sentence` just stores it to state. This keeps the tool simple and lets the LLM — which already has the original question and the scalar value in its message history — compose a natural answer without a second LLM call in the tool.

### Conditional edge for SQL Agent → Visualization Agent routing
LangGraph `add_conditional_edges` with a `route_after_sql` function: if `error_message` is set, route to `END`; otherwise route to `"visualization_agent"`. No supervisor node needed for two sequential agents.

### `chart_config` serialization in ChatService
`ChatService.ask()` calls `.model_dump()` on the `ChartConfig` object before building `AnalyticsResponse`, exactly as it calls `.to_dict(orient="records")` for `query_result`. `AnalyticsResponse.chart_config` remains `Optional[dict]`.

### Streamlit UI reads `chart_config` dict
The UI receives `chart_config` as a plain dict (JSON-deserialized). It branches on `chart_config["chart_type"]` to pick the Plotly call. `df` is reconstructed from `query_result` (already present in the response as `list[dict]`).

### No DB changes
No new tables, no SQLAlchemy model changes. The data model is unchanged.

---

## Files to Create

| File | Purpose |
|---|---|
| `app/schemas/chart_config.py` | `ChartConfig` Pydantic model |
| `app/utils/chart_helpers.py` | `classify_shape()` pure helper |
| `app/prompts/visualization_prompt.py` | `VISUALIZATION_SYSTEM_PROMPT` constant |
| `app/tools/visualization_tools.py` | `VisualizationTools` class (3 `@tool` closures) |
| `app/agents/visualization_agent.py` | `VisualizationAgent` class |
| `tests/schemas/test_chart_config.py` | ChartConfig validation tests |
| `tests/utils/test_chart_helpers.py` | `classify_shape()` scenario tests |
| `tests/agents/test_visualization_agent.py` | VisualizationTools unit tests |

## Files to Modify

| File | Change |
|---|---|
| `app/orchestration/state.py` | `chart_config: Optional[ChartConfig]` (import ChartConfig) |
| `app/orchestration/graph.py` | Add `visualization_agent` node; conditional edge after `sql_agent` |
| `app/services/chat_service.py` | Serialize `chart_config` via `.model_dump()` |
| `website/app.py` | Chart/metric/table rendering + PNG download button |
| `tests/orchestration/test_graph.py` | Cover new routing (success → visualization, error → END) |
| `tests/services/test_chat_service.py` | Cover `chart_config` serialization |
| `tests/ui/test_app.py` | Cover chart, metric, table, PNG-button rendering |

---

## Pydantic Schemas

### `app/schemas/chart_config.py` — new

```python
from typing import Literal, Optional
from pydantic import BaseModel

class ChartConfig(BaseModel):
    chart_type: Literal["bar", "line", "pie", "scatter", "table", "single_value"]
    x: Optional[str] = None      # x-axis col (bar/line/scatter) or names col (pie)
    y: Optional[str] = None      # y-axis col (bar/line/scatter) or values col (pie)
    title: str
    sentence: Optional[str] = None  # plain-language answer; single_value only
```

### `app/orchestration/state.py` — updated type

```python
# Change:
chart_config: Optional[dict]
# To:
chart_config: Optional[ChartConfig]  # import from app.schemas.chart_config
```

---

## Implementation Phases

### Phase 1 — Schema + shape classifier
**Goal:** `ChartConfig` model and `classify_shape()` utility tested in isolation.

1. Create `app/schemas/chart_config.py` with `ChartConfig`.
2. Create `app/utils/chart_helpers.py` with `classify_shape(columns, dtypes, row_count) -> dict`.
   - `classify_shape` heuristics (in priority order):
     - `row_count == 1` and `len(columns) == 1` → `single_value`
     - 1 string + 1 numeric col, name contains `share`/`percent`/`ratio`/`pct` → `pie`
     - 1 date/datetime + 1 numeric col → `line`
     - 1 string + 1 numeric col → `bar`
     - exactly 2 numeric cols → `scatter`
     - else → `table`
   - `dtypes` values are pandas dtype names (e.g. `"object"`, `"float64"`, `"int64"`, `"datetime64[ns]"`).
3. Update `app/orchestration/state.py`: import `ChartConfig`; change annotation.
4. Create `tests/schemas/test_chart_config.py` (validation scenarios from spec).
5. Create `tests/utils/test_chart_helpers.py` (all 6 shape scenarios).
6. **Gate:** `uv run ruff check . && uv run ruff format --check . && uv run pytest`

### Phase 2 — VisualizationTools + VisualizationAgent
**Goal:** Agent class and all three tools tested at the `.func` level (no real LLM).

1. Create `app/prompts/visualization_prompt.py` with `VISUALIZATION_SYSTEM_PROMPT`.
   - Instruct: call `analyze_shape` first; if `single_value` call `build_sentence` with a composed sentence; otherwise call `build_chart_config` with inferred type/columns/title.
   - Warn: never fabricate column names not present in the data.
2. Create `app/tools/visualization_tools.py` with `VisualizationTools`:

   **`analyze_shape`**
   ```python
   @tool
   def analyze_shape(state: Annotated[WorkflowState, InjectedState]) -> dict:
       """Inspect query_result shape and return chart_type, x, y."""
       qr = state["query_result"]
       dtypes = {col: str(dtype) for col, dtype in qr.dataframe.dtypes.items()}
       return classify_shape(qr.columns, dtypes, qr.row_count)
   ```

   **`build_chart_config`**
   ```python
   @tool
   def build_chart_config(
       chart_type: str, x: Optional[str], y: Optional[str], title: str,
       tool_call_id: Annotated[str, InjectedToolCallId],
   ) -> Command:
       """Assemble ChartConfig and write to WorkflowState."""
       config = ChartConfig(chart_type=chart_type, x=x, y=y, title=title)
       return Command(update={
           "chart_config": config,
           "messages": [ToolMessage(content=f"chart_type={chart_type}", tool_call_id=tool_call_id)],
       })
   ```

   **`build_sentence`**
   ```python
   @tool
   def build_sentence(
       sentence: str, title: str,
       tool_call_id: Annotated[str, InjectedToolCallId],
   ) -> Command:
       """Store plain-language sentence for a single-value result."""
       config = ChartConfig(chart_type="single_value", title=title, sentence=sentence)
       return Command(update={
           "chart_config": config,
           "messages": [ToolMessage(content=f"single_value: {sentence[:80]}", tool_call_id=tool_call_id)],
       })
   ```

3. Create `app/agents/visualization_agent.py` with `VisualizationAgent`:
   - Constructor: `__init__(self, llm: ChatGoogleGenerativeAI)`.
   - Instantiates `VisualizationTools()`; calls `create_agent(model=llm, tools=[...], system_prompt=VISUALIZATION_SYSTEM_PROMPT, state_schema=WorkflowState, name="visualization_agent")`.
   - Stores result in `self._agent`.
4. Create `tests/agents/test_visualization_agent.py` — test each tool via `.func`:
   - `analyze_shape`: inject mock `WorkflowState` dict with `QueryResult`; assert correct `chart_type`, `x`, `y` returned.
   - `build_chart_config`: call `.func(chart_type="bar", x="cat", y="sales", title="T", tool_call_id="tc1")`; assert `Command.update["chart_config"]` is a `ChartConfig`.
   - `build_sentence`: call `.func(sentence="Revenue is 1M", title="Revenue", tool_call_id="tc2")`; assert `chart_type=="single_value"` and `sentence` set.
   - `VisualizationAgent` construction: assert `_agent is not None`.
5. **Gate:** `uv run ruff check . && uv run ruff format --check . && uv run pytest`

### Phase 3 — Graph wiring + ChatService update
**Goal:** End-to-end routing works; `chart_config` serializes correctly in the response.

1. Update `app/orchestration/graph.py`:
   - Import and instantiate `VisualizationAgent`.
   - Add `route_after_sql(state: WorkflowState) -> str` function: returns `"visualization_agent"` if no `error_message`, else `END`.
   - Replace `builder.add_edge("sql_agent", END)` with `builder.add_conditional_edges("sql_agent", route_after_sql)`.
   - `builder.add_node("visualization_agent", visualization_agent._agent)`.
   - `builder.add_edge("visualization_agent", END)`.
   - Pass `llm` to `VisualizationAgent` constructor.
2. Update `app/services/chat_service.py`:
   - After reading `chart_config = result.get("chart_config")`, call `.model_dump()` if it is a `ChartConfig` instance (not `None`/`dict`):
     ```python
     chart_config_obj = result.get("chart_config")
     chart_config_dict = chart_config_obj.model_dump() if chart_config_obj else None
     ```
   - Pass `chart_config=chart_config_dict` to `AnalyticsResponse`.
3. Update `tests/orchestration/test_graph.py`:
   - Test that `sql_agent` success → `visualization_agent` → `END`.
   - Test that `sql_agent` error → `END` (visualization skipped).
4. Update `tests/services/test_chat_service.py`:
   - Test `chart_config` is serialized to dict via `.model_dump()` in the response.
   - Test `chart_config=None` when state has no `chart_config`.
5. **Gate:** `uv run ruff check . && uv run ruff format --check . && uv run pytest`

### Phase 4 — Streamlit UI + PNG export + kaleido
**Goal:** Charts render correctly; PNG export works.

1. Add `kaleido` dependency: `uv add kaleido`.
2. Update `website/app.py`:
   - After the existing SQL display block, read `chart_config = data.get("chart_config")`.
   - Branch on `chart_config["chart_type"]`:

     **`single_value`:**
     ```python
     st.metric(label=chart_config["title"], value=chart_config["sentence"])
     # No dataframe, no CSV button, no PNG button
     ```

     **`bar` / `line` / `pie` / `scatter`:**
     ```python
     import plotly.express as px
     import plotly.io as pio
     df = pd.DataFrame(query_result)
     # build fig based on chart_type
     st.plotly_chart(fig, use_container_width=True)
     timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
     st.download_button("Download PNG", data=pio.to_image(fig, format="png"),
                        file_name=f"chart_{timestamp}.png", mime="image/png")
     # CSV button remains below (still show dataframe + CSV for context)
     # OR omit dataframe for chart path — see note below
     ```

     **`table` or `chart_config is None`:**
     ```python
     # Existing dataframe + CSV button path (unchanged)
     ```

   > **Note on dataframe for chart path:** The current UI shows `st.dataframe` for all multi-row results. With charts, there are two options:
   > - (A) Show chart only (cleaner). Remove dataframe + CSV for the chart path.
   > - (B) Show chart above dataframe + CSV (more detail).
   >
   > **Decision: Option A** — chart path shows chart + PNG button only; `table` path shows dataframe + CSV only. The `single_value` path shows metric only. This matches the issue spec ("clearest form"). The CSV download remains available for the `table` path.

3. Update `tests/ui/test_app.py`:
   - Mock API response with `chart_config={"chart_type": "bar", "x": "category", "y": "sales", "title": "Sales"}` and assert Streamlit chart call occurs.
   - Mock `chart_config={"chart_type": "single_value", ...}` and assert `st.metric` is called.
   - Mock `chart_config={"chart_type": "table", ...}` and assert `st.dataframe` is called.
   - Assert PNG button absent for `single_value` and `table`.
4. **Gate:** `uv run ruff check . && uv run ruff format --check . && uv run pytest`

---

## Commit Strategy

Per project memory: commit after each phase once gates are green.

| Commit | Scope |
|---|---|
| `feat(chart-config): add ChartConfig schema and classify_shape helper` | Phase 1 |
| `feat(visualization-agent): add VisualizationTools and VisualizationAgent` | Phase 2 |
| `feat(graph): wire VisualizationAgent; serialize chart_config in ChatService` | Phase 3 |
| `feat(streamlit-ui): render charts, metric sentences, and PNG export` | Phase 4 |

---

## Quality Gate Commands

Run in this order before each commit:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

No build step. All three must pass — do not claim a phase done on red.

---

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| `InjectedState` not available in the installed LangGraph version | Check `from langgraph.prebuilt import InjectedState` imports cleanly before implementing; fall back to passing `query_result` metadata as explicit args if absent |
| `kaleido` PNG export fails (subprocess dependency) | Test `pio.to_image` in isolation; fall back to a placeholder message if kaleido is not available at runtime |
| `classify_shape` heuristics misclassify some result shapes | Heuristics are conservative — when in doubt, return `table`. The LLM's `analyze_shape` call always has the override path; the spec explicitly allows table as the fallback |
| Pie chart x/y mapping confusion | Document clearly in both `chart_helpers.py` and `visualization_prompt.py`: for pie, `x` = names column, `y` = values column |
