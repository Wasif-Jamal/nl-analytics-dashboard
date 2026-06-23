## Why

The SQL Agent (issue #1) returns `query_result` to `WorkflowState`, but nothing yet selects how to present it. FR-6, FR-7, and FR-8 are unmet: multi-row results are not visualised as charts, single-value results are not stated as a plain-language sentence, and there is no PNG export. The product is unusable as an analytics dashboard until this presentation layer exists.

## What Changes

- **`app/schemas/chart_config.py`** — new `ChartConfig` Pydantic model (`chart_type`, `x`, `y`, `title`, `sentence`) that carries the visualization decision from the agent to the UI.
- **`app/utils/chart_helpers.py`** — new `classify_shape()` pure helper that classifies a DataFrame's shape (row count, column types) into one of six chart types without LLM or Plotly involvement.
- **`app/prompts/visualization_prompt.py`** — new prompt constant for `VisualizationAgent`.
- **`app/tools/visualization_tools.py`** — new `VisualizationTools` class with three `@tool` closures: `analyze_shape` (reads state via `InjectedState`), `build_chart_config`, and `build_sentence`.
- **`app/agents/visualization_agent.py`** — new `VisualizationAgent` class as a `create_agent()` instance, following the same pattern as `SqlAgent`.
- **`app/orchestration/graph.py`** — updated to add a `visualization_agent` subgraph node with a conditional edge: success path routes `sql_agent → visualization_agent → END`; error path routes `sql_agent → END`.
- **`app/orchestration/state.py`** — `chart_config` type updated from `Optional[dict]` to `Optional[ChartConfig]`.
- **`app/services/chat_service.py`** — `ChatService.ask()` serializes `ChartConfig` to dict via `.model_dump()` before building `AnalyticsResponse`, matching the existing `query_result` serialization pattern.
- **`website/app.py`** — replaces the current single-value `st.metric` / multi-row `st.dataframe` branch with three branches driven by `chart_config["chart_type"]`: metric, Plotly chart + PNG download button, and table + CSV download button.
- **Tests** — new test files for `ChartConfig`, `classify_shape`, and `VisualizationTools`; updated tests for graph routing, ChatService serialization, and Streamlit rendering.

## Capabilities

### New Capabilities

- `visualization-agent`: VisualizationAgent as a `create_agent()` instance with `analyze_shape`, `build_chart_config`, and `build_sentence` internal tools. Reads `query_result` from `WorkflowState`; writes `ChartConfig` back via `Command`. Added as a subgraph node in `AnalyticsGraph`.

### Modified Capabilities

- `response-schema` (api-layer-fastapi) — `AnalyticsResponse.chart_config` now carries a serialized `ChartConfig` dict (previously always `None`). Additive; existing contract unchanged.
- `future-fields-ignored` (streamlit-ui) — replaced by four concrete rendering requirements: `single-value-rendering`, `chart-rendering`, `table-fallback-rendering`, and `png-export`.

## Design Decisions

- **`analyze_shape` uses `InjectedState`**: The tool needs the DataFrame's dtypes to distinguish string, numeric, and datetime columns — information the LLM's message history alone cannot reliably provide. `InjectedState` injects `WorkflowState` directly into the tool, the same injection mechanism already used for `InjectedToolCallId` in `execute_sql`.
- **`build_sentence` receives the LLM-composed sentence as an argument**: The agent LLM already has the scalar value and original question in its message history and is well-suited to composing a natural sentence. Having the tool receive the composed sentence (rather than performing a second LLM call inside the tool) keeps tools as thin side-effect executors and avoids nested LLM calls.
- **`AnalyticsResponse.chart_config` stays `Optional[dict]`**: The response schema is JSON-serialized; keeping the field as `dict` avoids any Pydantic serialization friction. `ChatService` calls `.model_dump()` on the in-process `ChartConfig` object before building the response — the same pattern used for `query_result → list[dict]`.
- **Graph uses a plain conditional edge, not a new supervisor**: Routing between two sequential agents (SQL → Visualization) requires only a `route_after_sql` function passed to `add_conditional_edges`. No supervisor node is needed at this stage; Insight and Follow-up agents will be added in later issues.
- **Chart path omits the dataframe**: When a chart is rendered, showing a redundant `st.dataframe` below it adds visual noise without adding value. The chart path renders chart + PNG button only; the table path renders dataframe + CSV button. The single-value path renders metric only.
- **`kaleido` added for PNG export**: `plotly.io.to_image("png")` requires kaleido. This is a lightweight static-image-generation package with no runtime service dependency.

## Impact

- New files: `app/schemas/chart_config.py`, `app/utils/chart_helpers.py`, `app/prompts/visualization_prompt.py`, `app/tools/visualization_tools.py`, `app/agents/visualization_agent.py`, `tests/schemas/test_chart_config.py`, `tests/utils/test_chart_helpers.py`, `tests/agents/test_visualization_agent.py`.
- Modified: `app/orchestration/state.py` (type annotation), `app/orchestration/graph.py` (new node + conditional edge), `app/services/chat_service.py` (chart_config serialization), `website/app.py` (rendering branches), `tests/orchestration/test_graph.py`, `tests/services/test_chat_service.py`, `tests/ui/test_app.py`.
- New dependency: `kaleido` (runtime, for PNG export).
- No DB schema changes; no new SQLAlchemy models; no new API routes.
