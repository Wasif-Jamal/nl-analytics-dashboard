# Spec: api-layer-fastapi

## Purpose

Defines the FastAPI HTTP layer — request/response schemas, endpoint contracts, the `ChatService` workflow bridge, session history management, application startup singleton construction, and error-response safety rules. Together these requirements govern all HTTP-level behaviour of the analytics dashboard backend.

---
## Requirements
### Requirement: request-schema
An analytics request SHALL be represented as `AnalyticsRequest` in `app/schemas/requests.py` with two required fields: `question` (non-empty string) and `session_uuid` (string identifying the caller's session). FastAPI validates the payload against this schema on every inbound request.

#### Scenario: valid request body
- **WHEN** the client submits `{"question": "Show monthly sales", "session_uuid": "abc-123"}`
- **THEN** `AnalyticsRequest` is constructed successfully and passed to the route handler

#### Scenario: missing required field
- **WHEN** the client omits `question` or `session_uuid` from the request body
- **THEN** FastAPI returns `422 Unprocessable Entity` with Pydantic validation details; `ChatService` is never called

#### Scenario: empty question string
- **WHEN** the client sends `{"question": "", "session_uuid": "abc-123"}`
- **THEN** FastAPI returns `422 Unprocessable Entity`; `ChatService` is never called

---

### Requirement: response-schema

`AnalyticsResponse` in `app/schemas/responses.py` SHALL include three additional `Optional` fields (defaulting to `None`) to carry serialized query rows to the UI:

| Field | Type | Notes |
|---|---|---|
| `query_result` | `Optional[list[dict]]` | Rows from `QueryResult.rows` (already `list[dict]`); `None` when no data was returned or an error occurred |
| `columns` | `Optional[list[str]]` | Ordered column names from `QueryResult.columns`; `None` when `query_result` is `None` |
| `row_count` | `Optional[int]` | Row count from `QueryResult.row_count`; `None` when `query_result` is `None` |

All previously defined fields (`question`, `generated_sql`, `sql_explanation`, `chart_config`, `insights`, `followup_questions`, `error_message`) are unchanged. The `session_history` field has been removed; the UI maintains the transcript client-side in `st.session_state`.

#### Scenario: successful workflow — query_result populated
- **WHEN** the workflow completes without error and `query_result` state is set
- **THEN** `AnalyticsResponse` is returned with `query_result` as a list of row dicts, `columns` as a list of column name strings, and `row_count` as an integer

#### Scenario: workflow error — query_result absent
- **WHEN** the workflow sets `error_message` in state (no data was retrieved)
- **THEN** `query_result`, `columns`, and `row_count` are all `None` in the response

---

### Requirement: submit-question-endpoint
`POST /api/chat` SHALL accept an `AnalyticsRequest`, delegate to `ChatService.ask()`, and return an `AnalyticsResponse`. The route contains no business logic.

#### Scenario: successful question submission
- **WHEN** `POST /api/chat` is called with a valid `AnalyticsRequest`
- **THEN** the route delegates to `ChatService.ask()` and returns `HTTP 200` with the `AnalyticsResponse` payload

#### Scenario: unknown route
- **WHEN** a client calls any path not defined in `app/routes/`
- **THEN** FastAPI returns `HTTP 404 Not Found`

---

### Requirement: health-endpoint
`GET /api/health` SHALL return `HTTP 200` with `{"status": "ok"}` unconditionally. It requires no dependencies and is safe to call before the workflow is ready.

#### Scenario: health check
- **WHEN** `GET /api/health` is called
- **THEN** `HTTP 200` is returned with body `{"status": "ok"}`

---

### Requirement: chat-service-workflow-bridge

`ChatService.ask()` SHALL serialize `state["query_result"]` into the three new response fields when the graph returns state without `error_message` and `query_result` is set.

#### Scenario: query_result in state — serialization
- **WHEN** `ChatService.ask()` reads final state with `query_result` set (a `QueryResult` object)
- **THEN** `AnalyticsResponse.query_result` is set to `query_result.rows`, `columns` to `query_result.columns`, and `row_count` to `query_result.row_count`

#### Scenario: query_result absent in state
- **WHEN** `ChatService.ask()` reads final state with `query_result` as `None` (error path or no data)
- **THEN** `AnalyticsResponse.query_result`, `columns`, and `row_count` remain `None`

### Requirement: session-history

`ChatService` SHALL maintain a process-wide in-memory `dict[str, list[ConversationTurn]]` keyed by `session_uuid`. On each successful workflow run it SHALL append a `ConversationTurn` built from the final `WorkflowState`. Errored runs (non-None `error_message`) are never appended. The `session_history` field has been removed from `AnalyticsResponse`; the UI maintains the rendered transcript in `st.session_state` client-side.

`ConversationTurn` is defined in `app/schemas/conversation.py` with fields: `question`, `generated_sql`, `sql_explanation`, `query_result`, `chart_config`, `insights`, `followup_questions`.

#### Scenario: first question in a new session — turn appended
- **WHEN** `ChatService.ask()` is called with a `session_uuid` that has no history and the workflow succeeds
- **THEN** a new entry is created for that `session_uuid` containing one `ConversationTurn`; `AnalyticsResponse` does not include a `session_history` field

#### Scenario: subsequent questions — turn appended
- **WHEN** `ChatService.ask()` is called with an existing `session_uuid` and the workflow succeeds
- **THEN** a new `ConversationTurn` is appended to the existing session list; the response does not include session history

#### Scenario: errored question — not appended
- **WHEN** `ChatService.ask()` is called and the workflow returns a non-None `error_message`
- **THEN** the session's `list[ConversationTurn]` is unchanged; no turn is appended

---

### Requirement: conversation-context-injection

Before each workflow run, `ChatService.ask()` SHALL read the current session's `list[ConversationTurn]` from the in-memory store and inject it as `conversation_history` in the initial `WorkflowState`. Only the current session's turns are ever read; no other session's turns are accessed.

#### Scenario: prior turns injected
- **WHEN** `ChatService.ask()` is called with a `session_uuid` that has N prior successful turns
- **THEN** `WorkflowState.conversation_history` is set to those N `ConversationTurn` objects before `_graph.invoke()` is called

#### Scenario: first turn — empty history
- **WHEN** `ChatService.ask()` is called for a session with no prior turns
- **THEN** `WorkflowState.conversation_history` is set to an empty list; the workflow proceeds normally

#### Scenario: cross-session isolation
- **WHEN** two sessions with different `session_uuid` values have concurrent turns
- **THEN** each invocation receives only its own session's `ConversationTurn` list; no cross-session data is ever read or passed to the LLM

---

### Requirement: startup-singleton
The compiled `AnalyticsGraph` and `ChatService` SHALL be constructed once inside `create_app()` and shared across all requests. Routes access `ChatService` via FastAPI's dependency-injection mechanism or a module-level reference set during startup.

#### Scenario: server starts
- **WHEN** `uv run uvicorn app.main:app` is executed
- **THEN** `create_app()` calls `AnalyticsGraph(...).build()` once, constructs `ChatService(graph)` once, and registers both routers (`/api/chat`, `/api/health`) before returning the `FastAPI` application

#### Scenario: concurrent requests
- **WHEN** multiple requests arrive simultaneously
- **THEN** they share the same compiled graph and `ChatService` instance; each invocation gets its own graph execution state (no shared mutable state between invocations)

---

### Requirement: error-response-safety
All application-level errors — both workflow `error_message` fields and unhandled exceptions — SHALL surface as `HTTP 200` responses with `error_message` set to a standard FRS §10 message. No stack traces, internal module paths, or raw exception messages SHALL appear in any API response.

#### Scenario: standard error messages only
- **WHEN** any error occurs during request processing
- **THEN** `error_message` in the response body is exactly one of: `"Unable to identify requested entities."`, `"Generated query could not be validated."`, `"No data found for the requested query."`, or `"Unable to retrieve data at this time."`

#### Scenario: no stack trace leakage
- **WHEN** an unhandled exception occurs inside `ChatService.ask()`
- **THEN** the `AnalyticsResponse` contains only the safe error message; the full exception is logged server-side only

