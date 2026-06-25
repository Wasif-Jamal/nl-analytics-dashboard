# api-layer-fastapi Spec Delta — Conversation History

## MODIFIED Requirements

### Requirement: session-history

`ChatService` SHALL maintain a process-wide in-memory `dict[str, list[ConversationTurn]]` keyed by `session_uuid`. On each successful workflow run it SHALL append a `ConversationTurn` built from the final `WorkflowState`. Errored runs (non-None `error_message`) are never appended. The `session_history` field is removed from `AnalyticsResponse`; the UI maintains the rendered transcript in `st.session_state` client-side.

`ConversationTurn` is defined in `app/schemas/conversation.py` with fields: `question`, `generated_sql`, `sql_explanation`, `query_result`, `chart_config`, `insights`, `followup_questions`.

*Previously: store was `dict[str, list[str]]`; `AnalyticsResponse` included `session_history: Optional[list[str]]` echoing question strings back to the UI.*

#### Scenario: first question in a new session — turn appended
- **WHEN** `ChatService.ask()` is called with a `session_uuid` that has no history and the workflow succeeds
- **THEN** a new entry is created for that `session_uuid` containing one `ConversationTurn`; `AnalyticsResponse` does **not** include a `session_history` field

#### Scenario: subsequent questions — turn appended
- **WHEN** `ChatService.ask()` is called with an existing `session_uuid` and the workflow succeeds
- **THEN** a new `ConversationTurn` is appended to the existing session list; the response does not include session history

#### Scenario: errored question — not appended
- **WHEN** `ChatService.ask()` is called and the workflow returns a non-None `error_message`
- **THEN** the session's `list[ConversationTurn]` is unchanged; no turn is appended

---

## ADDED Requirements

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
