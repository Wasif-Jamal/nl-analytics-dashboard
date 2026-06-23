# Spec Delta: api-layer-fastapi (result-presentation-charts)

## MODIFIED Requirements

### Requirement: response-schema

`AnalyticsResponse` in `app/schemas/responses.py` SHALL include `chart_config: Optional[dict]` (defaulting to `None`). When `chart_config` is set in workflow state, `ChatService.ask()` SHALL serialize the `ChartConfig` Pydantic object by calling `.model_dump()` and store the resulting dict in the response field.

All previously defined fields (`question`, `generated_sql`, `sql_explanation`, `query_result`, `columns`, `row_count`, `insights`, `followup_questions`, `error_message`, `session_history`) are unchanged.

#### Scenario: chart_config in state — serialized to response
- **WHEN** the workflow completes with `chart_config` set to a `ChartConfig` object in state
- **THEN** `AnalyticsResponse.chart_config` is set to `chart_config.model_dump()` — a plain dict containing `chart_type`, `x`, `y`, `title`, and `sentence`

#### Scenario: chart_config absent in state
- **WHEN** `chart_config` is `None` in final state (SQL error path or visualization not yet invoked)
- **THEN** `AnalyticsResponse.chart_config` is `None`

---

### Requirement: chat-service-workflow-bridge

`ChatService.ask()` SHALL serialize `state["chart_config"]` into `AnalyticsResponse.chart_config` when the graph returns a `ChartConfig` object in state.

#### Scenario: ChartConfig object serialized
- **WHEN** `ChatService.ask()` reads final state with `chart_config` as a `ChartConfig` instance
- **THEN** it calls `chart_config.model_dump()` and passes the result dict as `chart_config` to `AnalyticsResponse`

#### Scenario: chart_config None — no serialization
- **WHEN** `ChatService.ask()` reads final state with `chart_config=None`
- **THEN** `AnalyticsResponse.chart_config` is `None`; no `model_dump()` call is made
