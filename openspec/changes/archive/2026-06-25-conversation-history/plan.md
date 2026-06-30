# Plan: conversation-history implementation

## Context

Replace the query-history-panel design with a conversational chat UI and per-session multi-turn LLM context. Requirement source: FR-11 / FRS §6.7. Design source: `openspec/changes/conversation-history/proposal.md` and delta specs in `openspec/changes/conversation-history/specs/`.

The codebase is fully implemented. This change modifies 8 existing source files, creates 1 new schema file, and updates 2 test files. No DB or SQLAlchemy changes required.

---

## Architecture notes from codebase inspection

- **SQL Agent** uses `WorkflowState` directly as `state_schema`. Its `generate_sql` tool currently builds an inner LLM call using `SQL_SYSTEM_PROMPT`. To pass history: add `InjectedState` to `generate_sql` so it reads `conversation_history` from `WorkflowState`.
- **Analysis agents** (Insight, Visualization, Followup) use private `XAgentState` TypedDicts. Their `node()` methods bridge `WorkflowState → XAgentState`. To pass history: add `conversation_history` to each private state and tool-state TypedDict; `node()` forwards it; each tool reads + formats it into the inner prompt.
- **`session_history` removal**: 6 existing `test_chat_service.py` assertions and `_success_data()` in `test_app.py` reference this field and must be updated.
- **`st.chat_input`**: Streamlit `AppTest` supports `at.chat_input[0].set_value(...)`. The existing tests using `at.text_input[0]` and `at.button[0]` need updating to use the new chat input interaction.

---

## Exact files to create / modify

| # | File | Action |
|---|---|---|
| 1 | `app/schemas/conversation.py` | **CREATE** — `ConversationTurn` Pydantic model |
| 2 | `app/orchestration/state.py` | **MODIFY** — add `conversation_history` field |
| 3 | `app/schemas/responses.py` | **MODIFY** — remove `session_history` field |
| 4 | `app/prompts/sql_prompt.py` | **MODIFY** — add `SQL_HISTORY_TEMPLATE` constant |
| 5 | `app/prompts/insight_prompt.py` | **MODIFY** — add `{conversation_history}` slot to inner prompt |
| 6 | `app/prompts/visualization_prompt.py` | **MODIFY** — add `{conversation_history}` slot to inner prompt |
| 7 | `app/prompts/followup_prompt.py` | **MODIFY** — add `{conversation_history}` and `{prior_followups}` slots |
| 8 | `app/tools/sql_tools.py` | **MODIFY** — add `_SqlToolState`; add `InjectedState` to `generate_sql` |
| 9 | `app/tools/insight_tools.py` | **MODIFY** — add `conversation_history` to `_InsightToolState`; format in tool |
| 10 | `app/tools/visualization_tools.py` | **MODIFY** — add `conversation_history` to `_VisualizationToolState`; format in tool |
| 11 | `app/tools/followup_tools.py` | **MODIFY** — add `conversation_history` to `_FollowupToolState`; format + include prior followups |
| 12 | `app/agents/insight_agent.py` | **MODIFY** — add `conversation_history` to `InsightAgentState`; pass through in `node()` |
| 13 | `app/agents/visualization_agent.py` | **MODIFY** — add `conversation_history` to `VisualizationAgentState`; pass through in `node()` |
| 14 | `app/agents/followup_agent.py` | **MODIFY** — add `conversation_history` to `FollowupAgentState`; pass through in `node()` |
| 15 | `app/services/chat_service.py` | **MODIFY** — store shape, context injection, turn appending, remove `session_history` from response |
| 16 | `website/app.py` | **MODIFY** — replace text input/button → `st.chat_input`; add chat-layout rendering |
| 17 | `tests/services/test_chat_service.py` | **MODIFY** — update session-history tests; add context injection + turn appending tests |
| 18 | `tests/ui/test_app.py` | **MODIFY** — update input interactions; add chat-layout tests |
| 19 | `openspec/specs/api-layer-fastapi/spec.md` | **MODIFY** — sync delta spec (session-history requirement) |
| 20 | `openspec/specs/streamlit-ui/spec.md` | **MODIFY** — sync delta spec (question-submission + chat-layout) |

---

## Pydantic schema shapes

### `app/schemas/conversation.py` — new file

```python
class ConversationTurn(BaseModel):
    question:           str
    generated_sql:      Optional[str] = None
    sql_explanation:    Optional[str] = None
    query_result:       Optional[QueryResult] = None
    chart_config:       Optional[ChartConfig] = None
    insights:           Optional[list[str]] = None
    followup_questions: Optional[list[str]] = None
```

### `app/orchestration/state.py` — add one field

```python
from app.schemas.conversation import ConversationTurn

class WorkflowState(MessagesState):
    ...
    conversation_history: Optional[list[ConversationTurn]]  # None = first turn
```

### `app/schemas/responses.py` — remove one field

Remove: `session_history: list[str] = []` (and its docstring entry).

---

## History formatting (no new schema — string formatting in tools)

Each tool defines a module-level helper `_format_history(turns)` that renders a compact multi-line string. No new Pydantic model needed.

**SQL agent** (`generate_sql` inner call):
```
Prior conversation turns (for context):
[1] Q: "{question}" | SQL: "{generated_sql}"
[2] Q: "{question}" | SQL: "{generated_sql}"
```

**Insight + Visualization agents** (`generate_insights`, `select_visualization`):
```
Prior conversation turns (for context):
[1] Q: "{question}" | SQL: "{generated_sql}" | Key insights: {insights_summary}
```

**Followup agent** (`generate_followup_questions`) — additionally includes prior suggestions:
```
Prior conversation turns (already suggested — do not repeat these):
[1] Q: "{question}" | SQL: "{generated_sql}" | Suggested: {followup_questions_joined}
```

If `conversation_history` is empty or `None`, each prompt slot receives `"(none)"`.

---

## Chat Service changes (`app/services/chat_service.py`)

```python
# Store type change
_history: dict[str, list[ConversationTurn]] = {}

async def ask(self, request):
    prior_turns = self._history.get(request.session_uuid, [])
    result = await asyncio.to_thread(
        self._graph.invoke,
        {
            "question": request.question,
            "messages": [HumanMessage(content=request.question)],
            "conversation_history": prior_turns,   # <-- new
        },
    )
    # ... map state to response (no session_history field) ...
    if not error_message:
        turn = ConversationTurn(
            question=request.question,
            generated_sql=result.get("generated_sql"),
            sql_explanation=result.get("sql_explanation"),
            query_result=query_result_obj,
            chart_config=chart_config_obj,
            insights=result.get("insights"),
            followup_questions=result.get("followup_questions"),
        )
        self._history.setdefault(request.session_uuid, []).append(turn)
    return AnalyticsResponse(
        question=...,
        generated_sql=...,
        # session_history removed
        ...
    )
```

Exception path: remove `session_history=snapshot` from the fallback `AnalyticsResponse`.

---

## Streamlit UI changes (`website/app.py`)

### Key structural change

```python
# Initialize session state
if "turns" not in st.session_state:
    st.session_state.turns = []

# Render existing turns top-to-bottom
for i, turn in enumerate(st.session_state.turns):
    with st.chat_message("user"):
        st.markdown(turn["question"])
    with st.chat_message("assistant"):
        _render_answer(turn, turn_idx=i)

# Chat input fixed at bottom
question = st.chat_input("Ask a question about your data")
pending = st.session_state.pop("pending_question", None)
effective_question = pending or question

if effective_question:
    with st.chat_message("user"):
        st.markdown(effective_question)
    with st.chat_message("assistant"):
        with st.spinner("Analyzing..."):
            try:
                response = httpx.post(...)
                data = response.json()
                _render_answer(data, turn_idx=len(st.session_state.turns))
                st.session_state.turns.append(data)
            except httpx.ConnectError:
                st.warning("Could not connect to the server. Please try again.")
            except httpx.RequestError:
                st.warning("Could not connect to the server. Please try again.")
```

### `_render_answer(data, turn_idx)` — new helper

Extracts the existing if/else result rendering block. `turn_idx` is used to generate unique keys for follow-up buttons (`f"followup_{turn_idx}_{hash(q)}"`). Handles both error path (`st.warning`) and success path (SQL → chart/written answer → dataframe/CSV → insights → follow-up buttons).

### Reused helpers

`_build_figure()` and `_render_dataframe()` are unchanged and reused inside `_render_answer()`.

---

## Test changes

### `tests/services/test_chat_service.py`

**Remove** the 6 `resp.session_history` assertions (`test_first_question_appended_to_history`, `test_subsequent_questions_accumulate`, `test_workflow_error_not_appended_to_history`, `test_error_does_not_pollute_existing_history`, `test_exception_does_not_append_to_history`, and the inline `session_history=snapshot` check in `test_success_returns_populated_response`).

**Add new tests:**
- `test_graph_invoked_with_empty_conversation_history_on_first_call` — `mock_graph.invoke.call_args[0][0]["conversation_history"] == []`
- `test_conversation_turn_appended_on_success` — `service._history["sess"]` has 1 `ConversationTurn` with correct `question`
- `test_conversation_turn_not_appended_on_error` — `service._history` is empty after an error response
- `test_prior_turn_injected_on_second_call` — second call receives 1 turn in `conversation_history`
- `test_cross_session_isolation` — sess-A history not present in sess-B invocation's `conversation_history`

`_make_state()` helper gains an optional `conversation_history` key if needed for mock setup.

### `tests/ui/test_app.py`

**Update:**
- `_success_data()` — remove `"session_history": [question]`
- Tests using `at.text_input[0].set_value(...)` → `at.chat_input[0].set_value(...)`
- Tests using `at.button[0].click()` (submit button) → `at.chat_input[0].run()`
- `test_empty_question_shows_info_prompt` and `test_whitespace_question_shows_info_prompt` — `st.chat_input` natively ignores empty input (no HTTP call, no warning). Update to confirm that no warning or info is rendered when nothing is submitted.
- `test_usable_after_network_error` — remove `at.text_input` and `at.button` assertions; check `at.chat_input` is present instead.

**Add new tests:**
- `test_chat_input_present_on_first_load` — `len(at.chat_input) > 0` after initial render
- `test_empty_session_shows_no_bubbles` — no `st.chat_message` elements on first load
- `test_turns_accumulate_in_session_state` — after submit, `at.session_state["turns"]` has 1 entry

---

## No database changes

`ConversationTurn` is in-memory only. No SQLAlchemy models, no `database_initializer`, no migrations.

---

## Implementation order (dependency-safe)

1. `app/schemas/conversation.py` — defines `ConversationTurn` (base dep for everything)
2. `app/orchestration/state.py` — add `conversation_history` field
3. `app/schemas/responses.py` — remove `session_history`
4. `app/prompts/sql_prompt.py`, `insight_prompt.py`, `visualization_prompt.py`, `followup_prompt.py` — add history slots/templates
5. `app/tools/sql_tools.py`, `insight_tools.py`, `visualization_tools.py`, `followup_tools.py` — add `_XToolState` field + history formatting
6. `app/agents/insight_agent.py`, `visualization_agent.py`, `followup_agent.py` — add field to private state + `node()` passthrough
7. `app/services/chat_service.py` — store shape + context injection + turn appending
8. `website/app.py` — chat layout
9. `tests/services/test_chat_service.py` — update + extend
10. `tests/ui/test_app.py` — update + extend
11. `openspec/specs/api-layer-fastapi/spec.md` — sync delta
12. `openspec/specs/streamlit-ui/spec.md` — sync delta

---

## Quality gates (run before each commit)

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

All 3 must be green. No build step for Streamlit.
