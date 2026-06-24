# Plan: visualisation

Implements FR-6, FR-7, FR-8 by replacing the `VisualizationAgent` stub with a full
`create_agent()` instance, introducing `ChartConfig` as a typed Pydantic schema,
building Plotly chart rendering in the UI, and adding PNG export.

---

## Approach

Six sequential phases. Each phase has a clear output; quality gates run after phase 6.

```
Phase 1 — Schema + Utils       (ChartConfig, chart_helpers — no deps)
Phase 2 — State + ChatService  (WorkflowState field type, response serialization)
Phase 3 — Agent                (prompt, tools, agent — depends on phases 1+2)
Phase 4 — UI                   (chart rendering, written answer, PNG button)
Phase 5 — Dependency           (kaleido added via uv add)
Phase 6 — Tests                (visualization agent + chart helpers)
```

The graph wiring in `app/orchestration/graph.py` **does not change**: the graph already
registers `viz_agent.node` as a function node. The new implementation keeps the same
`.node()` interface.

---

## Phase 1 — Schema & Utils

### 1a. `app/schemas/chart_config.py` (NEW)

```python
from enum import Enum
from typing import Optional
from pydantic import BaseModel

class ChartType(str, Enum):
    bar = "bar"
    line = "line"
    pie = "pie"
    scatter = "scatter"
    table = "table"

class ChartConfig(BaseModel):
    chart_type: ChartType
    x_column: Optional[str] = None
    y_column: Optional[str] = None
    title: str = ""
    written_answer: Optional[str] = None
```

- `chart_type="table"` is the explicit fallback for ambiguous results and for all
  single-value (1×1) results.
- `written_answer` is set only when `chart_type="table"` and the result is a single
  scalar — the UI renders `st.info(written_answer)`.
- Used as the `with_structured_output` target inside `select_visualization` AND as the
  typed `WorkflowState.chart_config` field.

### 1b. `app/utils/chart_helpers.py` (NEW)

Module-level function, no class:

```python
def build_figure(chart_config: ChartConfig, rows: list[dict]) -> go.Figure | None:
```

Dispatch table:
| `chart_type` | Plotly call | Required columns |
|---|---|---|
| `bar` | `px.bar(df, x=x_column, y=y_column, title=title)` | both |
| `line` | `px.line(df, x=x_column, y=y_column, title=title)` | both |
| `pie` | `px.pie(df, names=x_column, values=y_column, title=title)` | both |
| `scatter` | `px.scatter(df, x=x_column, y=y_column, title=title)` | both |
| `table` | return `None` | — |

Guard: if `chart_type == table`, or `rows` is empty, or a required column is missing
from the row dicts → return `None` (no exception propagates).

---

## Phase 2 — State + ChatService

### 2a. `app/orchestration/state.py` (UPDATE)

Change one import and one field:

```python
# add import
from app.schemas.chart_config import ChartConfig

# change field (was Optional[dict])
chart_config: Optional[ChartConfig]
```

### 2b. `app/services/chat_service.py` (UPDATE)

In `ask()`, serialize `ChartConfig` → dict before building `AnalyticsResponse`:

```python
# replace: chart_config=result.get("chart_config"),
chart_config_obj = result.get("chart_config")
chart_config = chart_config_obj.model_dump() if chart_config_obj else None
# ...
return AnalyticsResponse(
    ...
    chart_config=chart_config,
    ...
)
```

`AnalyticsResponse.chart_config` remains `Optional[dict]` — no schema change there.

---

## Phase 3 — Agent

### 3a. `app/prompts/visualization_prompt.py` (UPDATE — fill from placeholder)

Two constants:

**`VISUALIZATION_SYSTEM_PROMPT`** — outer agent loop: instructs the LLM to call
`select_visualization` exactly once and stop.

**`VISUALIZATION_INNER_PROMPT`** — used inside the tool for the nested
`with_structured_output(ChartConfig)` call. Must include:
- The FRS §6.3 mapping table (result shape → chart type)
- Instruction: for 1×1 single-value, set `chart_type="table"` and write a
  natural-language sentence in `written_answer` (e.g. "Total revenue for Q1 is $842K")
- Instruction: for all other shapes, set `chart_type` to the best match; leave
  `written_answer` as null

### 3b. `app/tools/visualization_tools.py` (NEW)

Mirrors `InsightTools` / `FollowupTools` pattern exactly:

```python
class _VisualizationToolState(TypedDict, total=False):
    question: str
    query_result: Optional[QueryResult]

_MAX_VIZ_ROWS = 50

class VisualizationTools:
    def __init__(self, llm) -> None:
        @tool
        def select_visualization(
            tool_call_id: Annotated[str, InjectedToolCallId],
            state: Annotated[_VisualizationToolState, InjectedState()],
        ) -> Command:
            ...
        self.select_visualization = select_visualization
```

`select_visualization` logic:
1. Read `query_result` and `question` from injected state.
2. If `query_result` is `None` or `rows` is empty → return
   `Command(update={"chart_config": None, "messages": [ToolMessage("No data.", ...)]})`.
3. Cap rows at `_MAX_VIZ_ROWS = 10`; log warning if truncated.
4. Build nested prompt from `VISUALIZATION_INNER_PROMPT` (includes question, columns,
   row_count, and up to 50 rows as JSON).
5. Call `llm.with_structured_output(ChartConfig).invoke([HumanMessage(prompt)])`.
6. Return `Command(update={"chart_config": result, "messages": [ToolMessage(...)]})`.
7. On exception: log warning, return
   `Command(update={"chart_config": None, "messages": [ToolMessage("Failed.", ...)]})`.
   Do NOT set `error_message`.

### 3c. `app/agents/visualization_agent.py` (REPLACE stub)

Follows `InsightAgent` pattern exactly:

```python
class VisualizationAgentState(MessagesState):
    question: str
    query_result: Optional[QueryResult]
    chart_config: Optional[ChartConfig]

class VisualizationAgent:
    def __init__(self, llm) -> None:
        viz_tools = VisualizationTools(llm=llm)
        self._agent = create_agent(
            model=llm,
            tools=[viz_tools.select_visualization],
            system_prompt=VISUALIZATION_SYSTEM_PROMPT,
            state_schema=VisualizationAgentState,
            name="visualization_agent",
        )

    def node(self, state: WorkflowState) -> dict:
        result = self._agent.invoke({
            "messages": [HumanMessage(content="Select the best visualization.")],
            "question": state.get("question", ""),
            "query_result": state.get("query_result"),
        })
        return {"chart_config": result.get("chart_config")}
```

The outer `StateGraph` already registers `viz_agent.node` — **no graph change needed**.

---

## Phase 4 — Streamlit UI (`website/app.py`)

Replace the current single-value `st.metric` block and add chart rendering after the
SQL expander. The rendering order becomes:

1. SQL expander (unchanged)
2. **Visualization section** (new — driven by `chart_config`)
3. Results table + CSV download (unchanged for multi-row / table-only paths)
4. Insights panel (unchanged)
5. Suggested Questions (unchanged)

**Rendering logic** (pseudo-code):

```python
chart_config = data.get("chart_config")  # dict or None

if chart_config:
    written_answer = chart_config.get("written_answer")
    chart_type = chart_config.get("chart_type")

    if written_answer:
        # single-value path (replaces st.metric)
        st.info(written_answer)
        # no dataframe, no CSV, no PNG button

    elif chart_type in {"bar", "line", "pie", "scatter"}:
        from app.utils.chart_helpers import build_figure
        from app.schemas.chart_config import ChartConfig, ChartType
        config_obj = ChartConfig(**chart_config)
        fig = build_figure(config_obj, query_result or [])
        if fig:
            st.plotly_chart(fig, use_container_width=True)
            png_bytes = fig.to_image(format="png")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            st.download_button(
                label="Download PNG",
                data=png_bytes,
                file_name=f"chart_{timestamp}.png",
                mime="image/png",
            )
        else:
            # build_figure returned None (missing column etc.) — fall through to dataframe
            _render_dataframe(query_result, columns, row_count)

    else:
        # chart_type == "table" — fall through to dataframe
        _render_dataframe(query_result, columns, row_count)

else:
    # chart_config absent — existing behavior
    _render_dataframe(query_result, columns, row_count)
```

The existing metric (`st.metric`) path is **removed**. The new written-answer path
(`st.info`) handles all 1×1 results once `VisualizationAgent` is live.

> **Note:** The UI imports `ChartConfig` from `app.schemas.chart_config` to reconstruct
> the object from the API dict. This is the only place `website/app.py` imports from
> `app/` — it is acceptable because `ChartConfig` is a pure Pydantic schema with no
> LangGraph dependency.

---

## Phase 5 — Dependency

```bash
uv add kaleido
```

Required at runtime for `fig.to_image(format="png")`. Must be added before running
tests that exercise the PNG path.

---

## Phase 6 — Tests

### `tests/agents/test_visualization_agent.py` (NEW)

Mirrors `test_insight_agent.py` / `test_followup_agent.py` pattern — calls
`select_visualization.func(tool_call_id=..., state=...)` directly (bypasses tool
wrapper), mocks `llm.with_structured_output`.

| Test | What it verifies |
|---|---|
| `test_select_visualization_success_bar` | Multi-row → LLM called → `chart_config` set with `chart_type="bar"` |
| `test_select_visualization_single_value` | 1×1 → LLM called → `chart_type="table"`, `written_answer` set |
| `test_select_visualization_empty_rows` | `rows=[]` → no LLM call → `chart_config=None` |
| `test_select_visualization_no_query_result` | `query_result=None` → no LLM call → `chart_config=None` |
| `test_select_visualization_llm_failure` | LLM raises → `chart_config=None`, `error_message` NOT set |
| `test_select_visualization_rows_truncated` | 15 rows → only first 10 serialized (check via `mock_chain.invoke` call arg) |
| `test_visualization_agent_compiles` | `VisualizationAgent(mock_llm)._agent` is `CompiledStateGraph` |

### `tests/utils/test_chart_helpers.py` (NEW)

Pure unit tests, no mocks needed:

| Test | What it verifies |
|---|---|
| `test_build_figure_bar` | Returns `go.Figure` for `chart_type="bar"` with valid rows |
| `test_build_figure_line` | Returns `go.Figure` for `chart_type="line"` |
| `test_build_figure_pie` | Returns `go.Figure` for `chart_type="pie"` |
| `test_build_figure_scatter` | Returns `go.Figure` for `chart_type="scatter"` |
| `test_build_figure_table_returns_none` | Returns `None` for `chart_type="table"` |
| `test_build_figure_missing_column_returns_none` | Returns `None` when `x_column` absent from row dicts |
| `test_build_figure_empty_rows_returns_none` | Returns `None` when `rows=[]` |

---

## Files Touched

| File | Change | Phase |
|---|---|---|
| `app/schemas/chart_config.py` | **New** | 1a |
| `app/utils/chart_helpers.py` | **New** | 1b |
| `app/orchestration/state.py` | **Update** — field type | 2a |
| `app/services/chat_service.py` | **Update** — serialize ChartConfig | 2b |
| `app/prompts/visualization_prompt.py` | **Update** — fill prompts | 3a |
| `app/tools/visualization_tools.py` | **New** | 3b |
| `app/agents/visualization_agent.py` | **Replace stub** | 3c |
| `website/app.py` | **Update** — chart rendering | 4 |
| `pyproject.toml` / `uv.lock` | **Update** — add kaleido | 5 |
| `tests/agents/test_visualization_agent.py` | **New** | 6 |
| `tests/utils/test_chart_helpers.py` | **New** | 6 |

`app/orchestration/graph.py` — **no change** (graph already registers `viz_agent.node`).
`app/schemas/responses.py` — **no change** (`AnalyticsResponse.chart_config` stays `Optional[dict]`).

---

## Quality Gates

Run in order after phase 6 before any commit:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

All three must pass green.

---

## Commit Strategy

Per project convention (memory: commit per phase group, gates green first):

| Commit | Scope | Phases |
|---|---|---|
| `feat(visualisation): add ChartConfig schema and chart_helpers` | schema + utils | 1 |
| `feat(visualisation): wire ChartConfig type into WorkflowState and ChatService` | state + service | 2 |
| `feat(visualisation): implement VisualizationAgent with select_visualization tool` | agent + prompts | 3 |
| `feat(visualisation): render charts and written answers in Streamlit UI` | UI | 4 |
| `feat(visualisation): add visualization agent and chart_helpers tests` | tests | 6 |

(Phase 5 — `uv add kaleido` — is committed alongside phase 3 or 4 when first needed.)
