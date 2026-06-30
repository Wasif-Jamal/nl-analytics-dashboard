# streamlit-ui Spec Delta — Conversation History

## MODIFIED Requirements

### Requirement: question-submission

The UI SHALL use `st.chat_input` fixed at the bottom of the page as the sole question entry point. On submit, it POSTs `{"session_uuid": <uuid>, "question": <text>}` to `http://localhost:8000/api/chat`.

*Previously: text input + submit button (`st.text_input` + `st.button`).*

#### Scenario: valid question submitted via chat input
- **WHEN** the user types a non-empty question in `st.chat_input` and presses Enter
- **THEN** the app POSTs `{"session_uuid": <uuid>, "question": <text>}` to `http://localhost:8000/api/chat` with `Content-Type: application/json`

#### Scenario: empty question submitted
- **WHEN** the user presses Enter with an empty or whitespace-only chat input
- **THEN** no HTTP request is made; `st.chat_input` handles this natively (it does not fire on empty input)

#### Scenario: follow-up button clicked — submitted via chat flow
- **WHEN** the user clicks a suggested follow-up button
- **THEN** `st.session_state["pending_question"]` is set to that question string and `st.rerun()` is called; on the next render `pending_question` is cleared and the question is submitted through the `st.chat_input` flow as a new turn

---

## ADDED Requirements

### Requirement: chat-layout

The UI SHALL render the session conversation top-to-bottom using `st.chat_message` bubbles, with the `st.chat_input` fixed at the bottom. The transcript SHALL be accumulated in `st.session_state["turns"]` as a list of turn dicts.

Each turn dict contains: `question`, and the response fields (`generated_sql`, `query_result`, `columns`, `row_count`, `chart_config`, `insights`, `followup_questions`, `error_message`). On every page render, all turns in `st.session_state["turns"]` are rendered in order (oldest first) before the chat input.

User bubble: `st.chat_message("user")` containing `st.markdown(question)`. Assistant bubble: `st.chat_message("assistant")` containing SQL expander, chart/written answer, results table, CSV button, insights, and follow-up buttons — each conditional on non-None. A loading spinner (`st.spinner`) is shown inside the assistant bubble while the request is in flight.

#### Scenario: empty session — chat input ready
- **WHEN** the user opens the app for the first time
- **THEN** `st.session_state["turns"]` is an empty list; no bubbles are rendered; `st.chat_input` is visible and ready

#### Scenario: first question answered
- **WHEN** the user submits a question and the backend responds successfully
- **THEN** a user bubble (question) and an assistant bubble (full answer) are appended to `st.session_state["turns"]` and rendered; the chat input remains at the bottom

#### Scenario: multiple turns rendered in order
- **WHEN** the session contains N prior turns
- **THEN** all N user+assistant bubble pairs are rendered top-to-bottom (oldest first) before the chat input; scroll position allows the user to review the full conversation

#### Scenario: follow-up references an earlier turn
- **WHEN** the user submits a follow-up question that refers to a prior answer (e.g. "now show that by region")
- **THEN** the new turn is appended as a new user+assistant bubble pair; the backend uses `conversation_history` context to resolve the reference correctly
