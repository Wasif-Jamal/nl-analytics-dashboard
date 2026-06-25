# Proposal: conversation-history

## Summary

Replace the existing query-history-panel design with a full conversational chat experience backed by per-session, in-memory multi-turn context. The change touches four layers: schemas (new `ConversationTurn`, updated `WorkflowState`), the Chat Service (store shape + context injection), the four agent prompts (history formatting), and the Streamlit UI (chat layout replacing the text-input + submit button).

**FRS:** FR-11 (§6.7 Conversation History)
**Issue:** `docs/issues/09-conversation-history.md`

---

## Why

The previous design stored only question strings per session and echoed them back in the API response for a left-panel re-run affordance. The new product requirement is:

1. **Conversational chat UI** — turns stacked top-to-bottom (question → full answer), `st.chat_input` fixed at the bottom, no separate history panel.
2. **Multi-turn LLM context** — prior turns of the *current session* are injected into `WorkflowState` before each run so agents can resolve follow-ups (e.g. "now show that by region") against earlier answers.

---

## Design decisions

| Decision | Choice | Reason |
|---|---|---|
| `session_history` in `AnalyticsResponse` | **Remove** | UI maintains the transcript in `st.session_state`; the backend store is for LLM context only |
| `conversation_history` in `WorkflowState` | **Add as TypedDict field** `Optional[list[ConversationTurn]]` | Type-safe; agents read it via `InjectedState`; consistent with all other state fields |
| UI input model | **Replace** `question-submission` requirement with `st.chat_input` + new `chat-layout` requirement | The text input + submit button model is incompatible with the chat transcript layout |
| LLM context schema | **No separate schema** — agents derive the compact slice (question + generated_sql + insights; Follow-up agent adds prior followup_questions) from `ConversationTurn` inside their prompt templates | Avoids a second schema; prompt logic owns the serialisation detail |

---

## Spec deltas

### `app/schemas/` — new `ConversationTurn` schema

New Pydantic model `ConversationTurn` added to `app/schemas/workflow_state.py` (or a new `conversation.py`):

```
ConversationTurn
  question:           str
  generated_sql:      Optional[str]
  sql_explanation:    Optional[str]
  query_result:       Optional[QueryResult]
  chart_config:       Optional[ChartConfig]
  insights:           Optional[list[str]]
  followup_questions: Optional[list[str]]
```

### `app/orchestration/state.py` — `WorkflowState`

Add one field:

```
conversation_history: Optional[list[ConversationTurn]] = None
```

### `app/schemas/responses.py` — `AnalyticsResponse`

Remove `session_history: Optional[list[str]]`.

### `app/services/chat_service.py` — `ChatService`

- Store changes from `dict[str, list[str]]` → `dict[str, list[ConversationTurn]]`.
- Before each `_graph.invoke()` call: read current session's prior turns from the store and set `conversation_history` in the initial state.
- After successful workflow run: construct a `ConversationTurn` from the final state and append to the session's list.
- Errored runs (non-None `error_message`) are **not** appended.

### `app/prompts/` — four agent prompts updated

Each prompt receives a `{conversation_history}` template slot. The compact context per prior turn is:

- **SQL, Visualization, Insight agents:** `question` + `generated_sql` + `insights`
- **Follow-up agent:** same + `followup_questions`

Result rows are never included.

### `website/app.py` — Streamlit UI

- Replace text input + submit button with `st.chat_input`.
- Add `chat-layout` requirement: `st.session_state["turns"]` accumulates rendered turns; on each rerun the full list is rendered top-to-bottom using `st.chat_message`.
- Each turn renders: user bubble (question), assistant bubble (SQL expander, chart/written answer, results table, CSV button, insights, follow-up buttons).

---

## What Changes

- **`api-layer-fastapi`**: `session-history` requirement MODIFIED — store changes from `dict[str, list[str]]` to `dict[str, list[ConversationTurn]]`; `session_history` field removed from `AnalyticsResponse`. New `conversation-context-injection` requirement ADDED — prior turns injected into `WorkflowState` before each run; cross-session isolation enforced.
- **`streamlit-ui`**: `question-submission` requirement MODIFIED — `st.text_input` + `st.button` replaced by `st.chat_input`. New `chat-layout` requirement ADDED — `st.session_state["turns"]` accumulates turns; rendered top-to-bottom with `st.chat_message` bubbles.

Full delta specs are in `specs/api-layer-fastapi/spec.md` and `specs/streamlit-ui/spec.md`.

## Files Changed

| File | Change type |
|---|---|
| `app/schemas/conversation.py` (new) | Add `ConversationTurn` |
| `app/orchestration/state.py` | Add `conversation_history` field to `WorkflowState` |
| `app/schemas/responses.py` | Remove `session_history` |
| `app/services/chat_service.py` | Store shape + context injection + turn appending |
| `app/prompts/sql_prompt.py` | Add history slot |
| `app/prompts/visualization_prompt.py` | Add history slot |
| `app/prompts/insight_prompt.py` | Add history slot |
| `app/prompts/followup_prompt.py` | Add history slot (includes prior followup_questions) |
| `website/app.py` | Replace input model; add chat-layout rendering |
| `openspec/specs/api-layer-fastapi/spec.md` | Update `session-history` requirement |
| `openspec/specs/streamlit-ui/spec.md` | Replace `question-submission`; add `chat-layout` |

---

## Out of scope

- Cross-session / persistent history
- Database-backed storage
- Sending result rows to the LLM
- Sharing conversations across users
