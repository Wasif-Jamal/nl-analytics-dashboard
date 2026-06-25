## Requirement

Expose the analytics workflow over an HTTP API built with FastAPI, so the Streamlit UI (and any other client) submits questions and receives responses through well-defined endpoints. A Chat Service bridges the API and the LangGraph workflow. This is the design/infrastructure layer that carries FR-1 (submit questions) and response delivery. Source: SDS §9.3; `decisions/technical_architecture.md` §15.

> The Chat Service invokes the compiled `create_agent` graph produced by `AnalyticsGraph.build()` (issue #1) and manages in-memory per-session conversation history, injecting the current session's prior turns as context before each run (issue #9). The Streamlit UI (issue #3) consumes this API rather than invoking the workflow in-process.

## Acceptance Criteria

1. The FastAPI application is assembled in `app/main.py` and runs via `uv run uvicorn app.main:app`.
2. `app/routes/` exposes a submit-question endpoint (accepts an NL question + `session_uuid`, returns the analytics response) and a health endpoint.
3. Request and response payloads are validated by the Pydantic schemas in `app/schemas/requests` and `app/schemas/responses`.
4. Routes contain no business logic — they delegate to the Chat Service (`app/services/chat_service.py`).
5. The Chat Service invokes the compiled `create_agent` graph (issue #1) and returns the aggregated response; domain services remain independent of LangGraph.
6. The Chat Service maintains an in-memory `dict[session_uuid → list[ConversationTurn]]` history; successfully answered turns are appended, errored ones are not. Before each run it injects only that session's prior turns into the workflow as multi-turn context (issue #9).

## Error Scenarios

| Trigger | Expected result |
|---|---|
| Malformed / invalid request body | FastAPI returns a `422` validation error (Pydantic) |
| Workflow/backend raises during a request | API returns a safe error payload carrying the relevant standard FRS §10 message; no stack trace leaked |
| Request to an unknown route | `404 Not Found` |

## Out of Scope

- Authentication / authorization (FRS §13).
- The feature behaviors themselves (issues #1, #3–#9) — this issue is the transport/bridge only.
- Rate limiting, API versioning, and external/public exposure.
