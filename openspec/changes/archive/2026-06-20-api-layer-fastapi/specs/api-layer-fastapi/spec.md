## ADDED Requirements

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
An analytics response SHALL be represented as `AnalyticsResponse` in `app/schemas/responses.py` with the following fields (all analytics fields are `Optional` and default to `None`):

| Field | Type | Notes |
|---|---|---|
| `question` | `str` | Echo of the submitted question |
| `generated_sql` | `Optional[str]` | SQL produced by the SQL agent |
| `sql_explanation` | `Optional[str]` | Plain-English SQL explanation |
| `chart_config` | `Optional[dict]` | Visualization config (populated by issue #5) |
| `insights` | `Optional[list[str]]` | Data-grounded insights (populated by issue #6) |
| `followup_questions` | `Optional[list[str]]` | Suggested follow-ups (populated by issue #7) |
| `error_message` | `Optional[str]` | Standard FRS §10 message on failure; `None` on success |
| `session_history` | `list[str]` | Ordered list of successfully answered questions for this session |

The `HealthResponse` schema in the same module has a single field: `status: str`.

#### Scenario: successful analytics response
- **WHEN** the workflow completes without error
- **THEN** `AnalyticsResponse` is returned with `error_message=None`, `session_history` containing the current question (appended), and all populated state fields set

#### Scenario: workflow-error analytics response
- **WHEN** the workflow sets `error_message` in state
- **THEN** `AnalyticsResponse` is returned with `error_message` set to the standard FRS §10 message; `session_history` does NOT contain the current question

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
`ChatService` in `app/services/chat_service.py` SHALL be the sole component that invokes the compiled `create_agent` graph. It accepts a `CompiledStateGraph` via constructor injection. Its `ask(request: AnalyticsRequest) -> AnalyticsResponse` method runs the workflow and maps final state to the response schema.

#### Scenario: successful workflow invocation
- **WHEN** `ChatService.ask()` invokes the graph and the graph returns state with `error_message=None`
- **THEN** `AnalyticsResponse` is constructed from the final state fields; `question` is appended to the session history; `session_history` in the response reflects the updated list

#### Scenario: workflow sets error_message
- **WHEN** the graph returns state with `error_message` set (e.g. `"Unable to identify requested entities."`)
- **THEN** `AnalyticsResponse` is returned with `error_message` propagated; the question is NOT appended to session history; `session_history` is unchanged

#### Scenario: unhandled exception from graph
- **WHEN** the graph raises any exception during invocation
- **THEN** `ChatService` catches it, logs it, and returns `AnalyticsResponse` with `error_message="Unable to retrieve data at this time."` and HTTP 200; no stack trace is exposed; the question is NOT appended to session history

---

### Requirement: session-history
`ChatService` SHALL maintain an in-memory `dict[str, list[str]]` keyed by `session_uuid`. Only successfully answered questions (where `error_message` is `None` after the workflow completes) are appended.

#### Scenario: first question in a new session
- **WHEN** `ChatService.ask()` is called with a `session_uuid` that has no history and the workflow succeeds
- **THEN** a new entry is created for that `session_uuid` containing the question; `session_history` in the response contains exactly that one question

#### Scenario: subsequent questions in the same session
- **WHEN** `ChatService.ask()` is called with an existing `session_uuid` and the workflow succeeds
- **THEN** the question is appended to the existing history; `session_history` in the response contains all previously successful questions plus the current one

#### Scenario: errored question is not appended
- **WHEN** `ChatService.ask()` is called and the workflow returns `error_message` (or raises)
- **THEN** the session history for that `session_uuid` is unchanged; `session_history` in the response reflects the pre-call state

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
