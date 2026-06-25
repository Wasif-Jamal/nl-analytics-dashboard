# Tasks: conversation-history implementation

Source: `openspec/changes/conversation-history/plan.md`  
Feature: FR-11 / FRS §6.7 — Conversation History  
Branch: `feature/conversation-history`

---

## Phase 1 — Foundation

Establish the `ConversationTurn` schema and wire it into `WorkflowState`. Remove the stale `session_history` field from the API response. No agent or UI code changes yet.

- [ ] **1.1** Create `app/schemas/conversation.py` — define `ConversationTurn` Pydantic model with fields: `question: str`, `generated_sql`, `sql_explanation`, `query_result`, `chart_config`, `insights`, `followup_questions` (all Optional except `question`)
- [ ] **1.2** Modify `app/orchestration/state.py` — add `conversation_history: Optional[list[ConversationTurn]]` field to `WorkflowState`; import from `app.schemas.conversation`
- [ ] **1.3** Modify `app/schemas/responses.py` — remove `session_history: list[str] = []` field (and its docstring entry) from `AnalyticsResponse`

**Checkpoint 1:**
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## Phase 2 — Core implementation (all groups PARALLEL)

Prompts, tools, and agents can be updated independently within each group. All three groups can also be worked in parallel since they don't import each other.

### 2A — Prompts (PARALLEL)

Add history context slots to all four agent prompts.

- [ ] **2A.1** Modify `app/prompts/sql_prompt.py` — add `SQL_HISTORY_TEMPLATE` constant; add `{conversation_history}` slot in the system prompt for use in `generate_sql`
- [ ] **2A.2** Modify `app/prompts/insight_prompt.py` — add `{conversation_history}` slot to the inner insight prompt
- [ ] **2A.3** Modify `app/prompts/visualization_prompt.py` — add `{conversation_history}` slot to the inner visualization prompt
- [ ] **2A.4** Modify `app/prompts/followup_prompt.py` — add `{conversation_history}` and `{prior_followups}` slots to the follow-up prompt

### 2B — Tools (PARALLEL; depends on 1.1 + 2A)

Add `conversation_history` to each tool-state TypedDict and format prior turns into the prompt.

- [ ] **2B.1** Modify `app/tools/sql_tools.py` — add `_SqlToolState(TypedDict)` with `conversation_history` field; add `InjectedState[_SqlToolState]` parameter to `generate_sql`; call `_format_history(turns)` and inject into system prompt
- [ ] **2B.2** Modify `app/tools/insight_tools.py` — add `conversation_history` to `_InsightToolState`; define `_format_history()`; inject formatted history into the inner insight call
- [ ] **2B.3** Modify `app/tools/visualization_tools.py` — add `conversation_history` to `_VisualizationToolState`; define `_format_history()`; inject formatted history into the inner visualization call
- [ ] **2B.4** Modify `app/tools/followup_tools.py` — add `conversation_history` to `_FollowupToolState`; define `_format_history_with_followups()`; inject both prior turns and prior `followup_questions` into the inner follow-up call

### 2C — Agents (PARALLEL; depends on 2B)

Forward `conversation_history` from `WorkflowState` through each analysis agent's `node()` bridge.

- [ ] **2C.1** Modify `app/agents/insight_agent.py` — add `conversation_history` to `InsightAgentState`; forward it in `node()` from `WorkflowState`
- [ ] **2C.2** Modify `app/agents/visualization_agent.py` — add `conversation_history` to `VisualizationAgentState`; forward it in `node()` from `WorkflowState`
- [ ] **2C.3** Modify `app/agents/followup_agent.py` — add `conversation_history` to `FollowupAgentState`; forward it in `node()` from `WorkflowState`

**Checkpoint 2:**
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## Phase 3 — Integration

Wire the history store into the service layer and rebuild the Streamlit UI around `st.chat_input`.

- [ ] **3.1** Modify `app/services/chat_service.py`:
  - Change `_history` store type from `dict[str, list[str]]` → `dict[str, list[ConversationTurn]]`
  - Before each `_graph.invoke()`: read current session's prior turns; inject as `conversation_history` in initial `WorkflowState`
  - After successful run (no `error_message`): construct `ConversationTurn` from final state and append to session list
  - Remove `session_history=snapshot` from both the success and exception-path `AnalyticsResponse` construction

- [ ] **3.2** Modify `website/app.py`:
  - Initialize `st.session_state.turns = []` on first load
  - Replace `st.text_input` + `st.button("Submit")` with `st.chat_input("Ask a question about your data")`
  - Extract `_render_answer(data, turn_idx)` helper (moves existing chart/answer/table/insights/followup rendering; uses `f"followup_{turn_idx}_{hash(q)}"` for unique button keys)
  - Add `st.session_state.pop("pending_question", None)` → `effective_question` override for follow-up button flow
  - Render all prior turns top-to-bottom with `st.chat_message("user")` / `st.chat_message("assistant")` before the chat input
  - On new question: render user bubble + assistant bubble (with spinner), append `data` to `st.session_state.turns`

**Checkpoint 3:**
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## Phase 4 — Tests

Update broken tests; add new tests per spec scenario. One test per scenario where possible.

- [ ] **4.1** Modify `tests/services/test_chat_service.py`:
  - **Remove** 6 old `resp.session_history` assertions: `test_first_question_appended_to_history`, `test_subsequent_questions_accumulate`, `test_workflow_error_not_appended_to_history`, `test_error_does_not_pollute_existing_history`, `test_exception_does_not_append_to_history`, and the inline `session_history=snapshot` check in `test_success_returns_populated_response`
  - **Add** `test_graph_invoked_with_empty_conversation_history_on_first_call` — `conversation_history == []` in first invoke call
  - **Add** `test_conversation_turn_appended_on_success` — `service._history["sess"]` has 1 `ConversationTurn` with correct `question`
  - **Add** `test_conversation_turn_not_appended_on_error` — `service._history` is empty after error response
  - **Add** `test_prior_turn_injected_on_second_call` — second call receives 1 turn in `conversation_history`
  - **Add** `test_cross_session_isolation` — sess-A history not present in sess-B invocation's `conversation_history`

- [ ] **4.2** Modify `tests/ui/test_app.py`:
  - **Update** `_success_data()` — remove `"session_history": [question]` key
  - **Update** all `at.text_input[0].set_value(...)` → `at.chat_input[0].set_value(...)`
  - **Update** all `at.button[0].click()` (submit) → `at.chat_input[0].run()`
  - **Update** `test_empty_question_shows_info_prompt` / `test_whitespace_question_shows_info_prompt` — `st.chat_input` natively ignores empty input; update assertions to confirm no HTTP call or warning is rendered
  - **Update** `test_usable_after_network_error` — remove `at.text_input` / `at.button` checks; assert `at.chat_input` is present
  - **Add** `test_chat_input_present_on_first_load` — `len(at.chat_input) > 0` after initial render
  - **Add** `test_empty_session_shows_no_bubbles` — no `st.chat_message` elements on first load
  - **Add** `test_turns_accumulate_in_session_state` — after submit, `at.session_state["turns"]` has 1 entry

**Checkpoint 4:**
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## Phase 5 — OpenSpec sync

Merge the delta specs into the canonical spec files so the frozen spec reflects the implemented design.

- [ ] **5.1** Modify `openspec/specs/api-layer-fastapi/spec.md` — replace the old `session-history` requirement with the new `ConversationTurn`-based store + `conversation-context-injection` requirement (from `openspec/changes/conversation-history/specs/api-layer-fastapi.md`)
- [ ] **5.2** Modify `openspec/specs/streamlit-ui/spec.md` — replace old `question-submission` requirement with `st.chat_input` version; add `chat-layout` requirement (from `openspec/changes/conversation-history/specs/streamlit-ui.md`)

**Final checkpoint:**
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## Summary

| Phase | Files | Notes |
|---|---|---|
| 1 — Foundation | 3 | Sequential; `ConversationTurn` is the root dependency |
| 2A — Prompts | 4 | Fully parallel |
| 2B — Tools | 4 | Fully parallel; depends on Phase 1 + 2A |
| 2C — Agents | 3 | Fully parallel; depends on 2B |
| 3 — Integration | 2 | Sequential; `chat_service.py` then `app.py` |
| 4 — Tests | 2 | Sequential within file; can run together |
| 5 — OpenSpec sync | 2 | Parallel; docs only |
| **Total** | **20** | |
