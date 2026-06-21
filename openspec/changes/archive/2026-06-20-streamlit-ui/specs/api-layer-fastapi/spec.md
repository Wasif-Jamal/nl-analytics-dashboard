# Spec Delta: api-layer-fastapi (streamlit-ui change)

## Delta Summary

Extends `AnalyticsResponse` with three new `Optional` fields to carry serialized query rows to the Streamlit UI. All existing requirements are unchanged; this file records only the additions.

---

## MODIFIED Requirements

### Requirement: response-schema

`AnalyticsResponse` in `app/schemas/responses.py` SHALL include three additional `Optional` fields (defaulting to `None`) to carry serialized query rows to the UI:

| Field | Type | Notes |
|---|---|---|
| `query_result` | `Optional[list[dict]]` | Serialized rows — `QueryResult.dataframe.to_dict(orient="records")`; `None` when no data was returned or an error occurred |
| `columns` | `Optional[list[str]]` | Ordered column names from `QueryResult.columns`; `None` when `query_result` is `None` |
| `row_count` | `Optional[int]` | Row count from `QueryResult.row_count`; `None` when `query_result` is `None` |

All previously defined fields (`question`, `generated_sql`, `sql_explanation`, `chart_config`, `insights`, `followup_questions`, `error_message`, `session_history`) are unchanged.

#### Scenario: successful workflow — query_result populated
- **WHEN** the workflow completes without error and `query_result` state is set
- **THEN** `AnalyticsResponse` is returned with `query_result` as a list of row dicts, `columns` as a list of column name strings, and `row_count` as an integer

#### Scenario: workflow error — query_result absent
- **WHEN** the workflow sets `error_message` in state (no data was retrieved)
- **THEN** `query_result`, `columns`, and `row_count` are all `None` in the response

---

### Requirement: chat-service-workflow-bridge

`ChatService.ask()` SHALL serialize `state["query_result"]` into the three new response fields when the graph returns state without `error_message` and `query_result` is set.

#### Scenario: query_result in state — serialization
- **WHEN** `ChatService.ask()` reads final state with `query_result` set (a `QueryResult` object)
- **THEN** `AnalyticsResponse.query_result` is set to `query_result.dataframe.to_dict(orient="records")`, `columns` to `query_result.columns`, and `row_count` to `query_result.row_count`

#### Scenario: query_result absent in state
- **WHEN** `ChatService.ask()` reads final state with `query_result` as `None` (error path or no data)
- **THEN** `AnalyticsResponse.query_result`, `columns`, and `row_count` remain `None`
