# Tasks: suggested-followup-questions

Sequenced from `plan.md`. Phases match the plan's dependency order.
Quality gate runs after each phase — all three commands must be green before
moving to the next phase.

```bash
# Quality gate (run after every phase)
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

No changes needed to `graph.py`, `chat_service.py`, `WorkflowState`, or
`AnalyticsResponse` — all wiring is already in place.

---

## Phase 1 — Foundation (schemas + prompts)

No inter-dependencies. Both tasks are PARALLEL.

- [ ] **T1** Create `app/schemas/followup_result.py`
  - `FollowupOutput(BaseModel)` with `followup_questions: list[str] = Field(..., min_length=1)`
  - Module docstring naming the contract; class docstring describing the exactly-3 constraint

- [ ] **T2** Update `app/prompts/followup_prompt.py`
  - Replace `FOLLOWUP_SYSTEM_PROMPT = ""` with the real outer prompt:
    - Direct the agent to call `generate_followup_questions` exactly once and stop
  - Add `FOLLOWUP_INNER_PROMPT` — template with `{question}` and `{rows_json}` placeholders:
    - Propose exactly 3 follow-up questions grounded in the current result
    - Each question must be independently executable as a new query
    - No filler or generic prompts; return empty list if none can be derived
  - Keep module docstring current

### ✅ Phase 1 checkpoint
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## Phase 2 — Core Implementation

T3 (tools) must complete before T4 (agent) — agent imports tools.

- [ ] **T3** Create `app/tools/followup_tools.py`
  - `_FollowupToolState(TypedDict, total=False)` — only `question: str` and
    `query_result: Optional[QueryResult]`; same rationale as `_InsightToolState`:
    using `WorkflowState` would cause Pydantic validation errors because the tool
    runs under `FollowupAgentState`, not `WorkflowState`
  - `FollowupTools` class; injects `llm` via constructor
  - `generate_followup_questions` `@tool` closure stored as `self.generate_followup_questions`
    - Params: `tool_call_id: Annotated[str, InjectedToolCallId]`,
      `state: Annotated[_FollowupToolState, InjectedState()]`
    - `_MAX_FOLLOWUP_ROWS = 50`; truncate `query_result.rows[:50]`; log warning if dropped
    - Empty/`None` `query_result`: return `Command(update={"followup_questions": [], "messages": [ToolMessage(content="No data.", ...)]})` — no LLM call
    - Happy path: format `FOLLOWUP_INNER_PROMPT`, call `llm.with_structured_output(FollowupOutput).invoke([HumanMessage(...)])`, return `Command(update={"followup_questions": result.followup_questions, "messages": [ToolMessage(...)]})`
    - LLM exception: log warning, return `Command(update={"followup_questions": [], ...})` — **do NOT set `error_message`**
  - Module + class docstrings naming `_FollowupToolState` and `FollowupOutput` contracts

- [ ] **T4** Update `app/agents/followup_agent.py` — replace stub with `create_agent()` instance
  - Remove the stub class body entirely; replace with:
  - `FollowupAgentState(MessagesState)` — private state with `question: str`,
    `query_result: Optional[QueryResult]`, `followup_questions: Optional[list[str]]`
  - `FollowupAgent.__init__(llm)`:
    - Instantiate `FollowupTools(llm=llm)`
    - Call `create_agent(model=llm, tools=[followup_tools.generate_followup_questions], system_prompt=FOLLOWUP_SYSTEM_PROMPT, state_schema=FollowupAgentState, name="followup_agent")` → `self._agent`
    - Log `FollowupAgent initializing` / `FollowupAgent compiled`
  - `FollowupAgent.node(state: WorkflowState) -> dict`:
    - Invoke `self._agent` with fresh `FollowupAgentState`:
      `{"messages": [HumanMessage("Suggest follow-up questions for the query results.")], "question": state.get("question", ""), "query_result": state.get("query_result")}`
    - Return `{"followup_questions": result.get("followup_questions")}`
  - Update module docstring to reflect real implementation

### ✅ Phase 2 checkpoint
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## Phase 3 — Tests

One pytest test per spec scenario. All tasks are PARALLEL.

- [ ] **T5** Create `tests/agents/test_followup_agent.py`

  **Tool call pattern** — call `.func` directly (bypasses LangChain wrapper):
  ```python
  command = tools.generate_followup_questions.func(
      tool_call_id="tc1",
      state={"query_result": _QUERY_RESULT, "question": "Show revenue by region", "messages": []},
  )
  ```

  **LLM mock pattern**:
  ```python
  mock_chain = MagicMock()
  mock_chain.invoke.return_value = FollowupOutput(followup_questions=["q1", "q2", "q3"])
  mock_llm = MagicMock()
  mock_llm.with_structured_output.return_value = mock_chain
  ```

  | Test | Spec scenario |
  |---|---|
  | `test_generate_followup_questions_success` | `query_result` present → LLM called once → `followup_questions` list in `Command.update`; `ToolMessage` present |
  | `test_generate_followup_questions_empty_rows` | `query_result.rows == []` → LLM NOT called → `followup_questions=[]` |
  | `test_generate_followup_questions_none_result` | `query_result is None` → LLM NOT called → `followup_questions=[]` |
  | `test_generate_followup_questions_llm_exception` | LLM raises → `followup_questions=[]`; `error_message` NOT in `Command.update` (or `None`) |
  | `test_generate_followup_questions_row_truncation` | 60 rows in state → only 50 serialized in prompt (parse `rows_json` from the `HumanMessage` content passed to `mock_chain.invoke`) |
  | `test_followup_agent_compiles` | `FollowupAgent(llm)._agent` is a `CompiledStateGraph` |
  | `test_followup_agent_node_invokes_agent_with_fresh_state` | `node()` passes exactly 1 `HumanMessage` + correct `question` + `query_result`; returns only `{"followup_questions": [...]}` |
  | `test_followup_agent_node_returns_only_followup_questions` | `node()` result dict has no `messages`, `question`, or `query_result` keys — only `followup_questions` (spec: `schema is not stored in WorkflowState`) |
  | `test_followup_tools_attribute_set` | `FollowupTools(llm).generate_followup_questions` is not `None` |

### ✅ Phase 3 checkpoint
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## Phase 4 — UI Integration

- [ ] **T6** Update `website/app.py`

  **4a — Session state initialisation** (add after the `session_uuid` block):
  ```python
  if "pending_question" not in st.session_state:
      st.session_state.pending_question = ""
  ```

  **4b — Submit logic** (replace `question = st.text_input(...)` and `submitted = st.button(...)`):
  ```python
  pending = st.session_state.pending_question
  auto_submit = bool(pending)
  if auto_submit:
      st.session_state.pending_question = ""

  question = st.text_input("Ask a question about your data", value=pending)
  submitted = st.button("Submit") or auto_submit
  ```

  **4c — Effective question** (inside `if submitted:`, replace all uses of `question` with
  `effective_question`):
  ```python
  effective_question = pending if auto_submit else question
  if not effective_question.strip():
      st.info("Please enter a question")
  else:
      # ... use effective_question everywhere (json body, display, etc.)
  ```

  **4d — Suggested Questions section** (after the existing insights block, still inside
  the `else` / no-error branch):
  ```python
  followup_questions = data.get("followup_questions") or []
  if followup_questions:
      st.subheader("Suggested Questions")
      for q in followup_questions:
          if st.button(q, key=f"followup_{hash(q)}"):
              st.session_state.pending_question = q
              st.rerun()
  ```

  **Manual verification checklist** (pytest cannot exercise Streamlit rendering):
  - [ ] Suggested Questions section appears after insights when `followup_questions` is non-empty
  - [ ] Section absent when `followup_questions` is `None` or `[]`
  - [ ] Clicking a button pre-fills the question input and auto-submits on next render
  - [ ] Section not shown when `error_message` is set
  - [ ] `chart_config` still silently ignored (no new panel appears)

### ✅ Phase 4 checkpoint (final gate)
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## Commit Plan

Per project convention: commit after each phase group once gates are green.

| Commit | Tasks | Message |
|---|---|---|
| 1 | T1–T2 | `feat(followup-pipeline): add FollowupOutput schema and prompts` |
| 2 | T3 | `feat(followup-pipeline): add FollowupTools with generate_followup_questions` |
| 3 | T4 | `feat(followup-pipeline): implement FollowupAgent replacing stub` |
| 4 | T5 | `test(followup-pipeline): add unit tests for FollowupAgent and FollowupTools` |
| 5 | T6 | `feat(streamlit-ui): add Suggested Questions section with one-click re-submission` |
