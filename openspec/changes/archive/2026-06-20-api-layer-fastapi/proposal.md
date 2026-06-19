## Why

The SQL pipeline (issue #1) produces a fully working LangGraph supervisor, but it has no HTTP surface. Every caller would have to instantiate `AnalyticsGraph`, wire dependencies, and manage session history themselves. This change adds the transport layer that all future clients — the Streamlit UI (issue #3) and any integration tests — talk to.

Without this layer the product cannot be used end-to-end: Streamlit must invoke the workflow in-process, which breaks the layered architecture and couples the UI to LangGraph internals.

## What Changes

- **`app/schemas/requests.py`** — new `AnalyticsRequest(question: str, session_uuid: str)`; Pydantic validates on ingress.
- **`app/schemas/responses.py`** — new `AnalyticsResponse` (full contract: `question`, `generated_sql`, `sql_explanation`, `chart_config`, `insights`, `followup_questions`, `error_message`, `session_history`) and `HealthResponse`. All analytics fields are `Optional` so the contract is stable from day one; future agents (issues #5–#7) just populate them.
- **`app/services/chat_service.py`** — new `ChatService` class; the single component that invokes the compiled `create_agent` graph; maintains an in-memory `dict[session_uuid → list[question]]` history; catches all unhandled exceptions and maps them to the standard FRS §10 error message.
- **`app/routes/chat_routes.py`** — new FastAPI router; `POST /api/chat`; delegates entirely to `ChatService`; no business logic.
- **`app/routes/health.py`** — new FastAPI router; `GET /api/health`; returns `{"status": "ok"}`.
- **`app/starter.py`** — updated: builds `AnalyticsGraph` + `ChatService` once at startup (singleton); registers both routers.
- **Tests** — unit tests for `ChatService` (mocked graph); API-level tests via FastAPI `TestClient` covering the happy path, workflow errors, and validation errors.

## Capabilities

### New Capabilities

- `submit-question-endpoint`: `POST /api/chat` accepts an NL question and session UUID, runs the analytics workflow, returns the full result payload including session history.
- `health-endpoint`: `GET /api/health` returns `{"status": "ok"}` for liveness checks.
- `session-history`: In-memory per-session question log; successfully answered questions are appended; errored ones are not.

### Modified Capabilities

- `sql-pipeline` (existing) — unchanged in behaviour; `ChatService` is its new sole external caller.

## Design Decisions

- **All errors → HTTP 200 with `error_message`**: Both workflow-level errors (state field set) and unhandled exceptions are mapped to standard FRS §10 messages in the response body. Transport always succeeds; errors live in the payload. This matches how the Streamlit UI (issue #3) will render errors inline rather than as HTTP failures.
- **Startup singleton**: `AnalyticsGraph.build()` is called once inside `create_app()`. The compiled graph and `ChatService` are reused for all requests, avoiding per-request compilation overhead. The `SqlAgent` design (inner state per invocation, no shared mutable dict) already ensures this is safe under concurrent requests.
- **Full response contract now**: `chart_config`, `insights`, and `followup_questions` are included as `Optional` fields with `None` defaults. The Streamlit UI can be built against this stable schema; future issues fill in the values.
- **Route prefix `/api`**: Clean namespace without version locking. `POST /api/chat`, `GET /api/health`.

## Impact

- New files: `app/schemas/requests.py`, `app/schemas/responses.py`, `app/services/chat_service.py`, `app/routes/chat_routes.py`, `app/routes/health.py`, `tests/services/test_chat_service.py`, `tests/routes/__init__.py`, `tests/routes/test_chat_routes.py`.
- Modified: `app/starter.py` (adds graph/service construction + router registration).
- No changes to `app/orchestration/`, `app/agents/`, `app/repositories/`, or `app/schemas/sql_result.py`.
