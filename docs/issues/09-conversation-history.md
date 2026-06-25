## Requirement

The system must keep a session-level, in-memory **conversation history** of each question a user asks and the answer it produced, render that conversation in a chat layout, and feed the prior turns of the **current session** back to the agents as context for multi-turn follow-ups. History is managed by the **Chat Service** in a server-side in-memory store keyed by a session UUID supplied by the Streamlit UI on every request. It is never written to or read from the database. Source: FRS §6.7, §7; FR-11.

> The Chat Service (`app/services/chat_service.py`) invokes the compiled `create_agent` graph (issue #1) and appends each successfully answered turn to the in-memory history for that session UUID. Before invoking the graph it injects that same session's prior turns into the workflow so the agents have conversational context. Turns that result in a non-`None` `error_message` in the final `WorkflowState` are surfaced in the chat but are never appended to the context history.

## Design

### Storage (Chat Service)

- The Chat Service maintains a process-wide in-memory `dict[session_uuid → list[ConversationTurn]]` that lives for the entire run of the application and is lost on restart. It is never persisted to SQLite.
- `ConversationTurn` is a Pydantic schema (in `app/schemas/`) capturing a completed turn: `question`, `generated_sql`, `sql_explanation`, `query_result`, `chart_config`, `insights`, `followup_questions`.
- The store is **per session**: every read is scoped to the request's `session_uuid`. Turns from other session UUIDs are never read, combined, or sent to the LLM.

### Multi-turn context for the agents

- On each request, before running the workflow, the Chat Service reads the current session's prior turns and injects them into the initial `WorkflowState` (a new `conversation_history` field) so the agents can use them.
- All four agents receive the history. The compact context payload sent to the LLM per prior turn is **`question` + `generated_sql` + `insights`** — result rows are not sent (the SQL conveys what was retrieved; this keeps the prompt bounded).
- The **Follow-up agent** additionally receives prior turns' `followup_questions` so it avoids re-suggesting questions already offered this session. The SQL, Visualization, and Insight agents do not receive prior follow-ups.
- Each agent formats its history slice via its own prompt (`app/prompts/`); history is never hardcoded into agent code.

### Conversational UI (Streamlit)

- The UI generates a `session_uuid` (UUID4) on first load, stores it in `st.session_state`, and sends it with every request.
- There is **no left history panel**. The page renders the conversation top-to-bottom: for each turn, the user's question followed by its answer (written sentence or chart, results table, insights, suggested follow-ups), oldest at the top, newest at the bottom.
- A chat input box is fixed at the bottom of the page (`st.chat_input`); submitting it POSTs `{session_uuid, question}` to the backend and appends the new turn to the transcript.
- The UI keeps the rendered transcript in `st.session_state` (it appends each response). The backend store is the source of truth for **LLM context**, not for display; the API response carries the current turn's answer, not the whole history.
- Clicking a suggested follow-up (issues #8 / #10 wiring) submits it as a new chat turn through the normal flow.

## Acceptance Criteria

1. The Streamlit UI generates a `session_uuid` on first load and passes it with every request.
2. The conversation is rendered in chat style: question then answer, ordered oldest to newest, with the input box at the bottom of the page.
3. The Chat Service appends each successfully answered turn to the in-memory history for that session UUID.
4. On each request the Chat Service injects only the current session's prior turns into the workflow, and the agents receive them as context (`question` + `generated_sql` + `insights`; the Follow-up agent also gets prior `followup_questions`).
5. A follow-up that references an earlier turn (e.g. "now show that by region") is answered using the conversational context.
6. History from one `session_uuid` is never read into, combined with, or sent to the LLM for any other session.
7. Submitting a suggested follow-up runs it as a new turn through the normal flow.
8. History is process-scoped, in-memory only, and never written to or read from SQLite.

## Error Scenarios

| Trigger | Expected result |
|---|---|
| No questions have been asked yet | The page shows an empty conversation with the input box ready |
| A question results in an error | The error message (issue #10) is shown inline as that turn's answer, but the turn is not appended to the context history |
| A re-run / follow-up turn fails downstream | Handled by the standard error flow (issue #10); prior successful turns remain in the transcript and context |

## Out of Scope

- Cross-session / persistent history (FRS §13–14).
- Sharing conversations with other users (FRS §14).
- Database-backed history storage of any kind.
- Sending prior turns' result rows to the LLM (only question + SQL + insights, plus follow-ups for the Follow-up agent, are sent).
