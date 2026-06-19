## Requirement

The system must keep a session-level, in-memory history of the questions a user has asked, and let them view and re-run previous questions. History is managed by the **Chat Service** in a server-side in-memory store keyed by a session UUID supplied by the Streamlit UI on every request. It is never written to or read from the database. Source: FRS §6.7, §7; FR-11.

> The Chat Service (`app/services/chat_service.py`) invokes the compiled `create_agent` graph (issue #11) and appends each successfully answered question to the in-memory history for that session UUID. Questions that result in a non-`None` `error_message` in the final `WorkflowState` are never appended.

## Design

- The Streamlit UI generates a `session_uuid` (UUID4) on first load and stores it in `st.session_state`. It is sent with every API request as part of the request payload.
- The Chat Service maintains an in-memory `dict[session_uuid → list[question]]`. After each successful workflow run it appends the question to the relevant list.
- The analytics response includes the current session history so the UI can render it without a separate API call.
- History is process-scoped: it is lost on server restart and is never persisted to SQLite.

## Acceptance Criteria

1. The Streamlit UI generates a UUID on first load and passes it with every request.
2. The Chat Service appends each successfully answered question to the in-memory history for that session UUID.
3. The analytics API response includes the session history list.
4. The Query History panel in the UI renders the history from the response; selecting an entry re-runs it through the normal flow.
5. History reflects the execution order within the active session.
6. History is never written to or read from the SQLite database.

## Error Scenarios

| Trigger | Expected result |
|---|---|
| No questions have been run yet | History panel shows an empty state |
| A question results in an error | It is not appended to history; the error is surfaced via issue #9 |
| A re-run history entry fails downstream | Handled by the standard error flow (issue #9) |

## Out of Scope

- Cross-session / persistent history (FRS §13–14).
- Sharing history with other users (FRS §14).
- Database-backed history storage of any kind.
