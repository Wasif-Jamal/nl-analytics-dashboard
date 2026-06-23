# Plan: suggested-followup-questions

## Scope

Replace the `FollowupAgent` stub with a real `create_agent()` implementation and wire
the Streamlit UI to render one-click follow-up question buttons. All wiring is already
in place: `graph.py` imports `FollowupAgent` and calls `followup_agent.node`; `chat_service.py`
already reads `followup_questions` from state and passes it to `AnalyticsResponse`; no
changes needed to `WorkflowState`, `AnalyticsResponse`, `graph.py`, or `chat_service.py`.

---

## Files

| File | Action | Notes |
|---|---|---|
| `app/schemas/followup_result.py` | **Create** | `FollowupOutput` Pydantic schema |
| `app/prompts/followup_prompt.py` | **Modify** | Replace empty string with real prompts |
| `app/tools/followup_tools.py` | **Create** | `FollowupTools` + `generate_followup_questions` |
| `app/agents/followup_agent.py` | **Modify** | Replace stub with `create_agent()` instance |
| `tests/agents/test_followup_agent.py` | **Create** | Unit tests mirroring `test_insight_agent.py` |
| `website/app.py` | **Modify** | Add Suggested Questions section; update submit logic |

No other files change.

---

## Phase 1 — Schema: `app/schemas/followup_result.py`

Mirror of `app/schemas/insight_result.py`. New file.

```python
class FollowupOutput(BaseModel):
    """Structured output from the follow-up question generation LLM call.

    Attributes:
        followup_questions: Exactly 3 concise follow-up question strings,
            each independently executable as a new query through the normal flow.
            Grounded only in the current result — no filler or fabricated prompts.
    """
    followup_questions: list[str] = Field(..., min_length=1)
```

**Quality gate:** `uv run ruff check .` → `uv run ruff format --check .` → `uv run pytest`
**Commit:** `feat(followup-pipeline): add FollowupOutput schema`

---

## Phase 2 — Prompts: `app/prompts/followup_prompt.py`

Replace `FOLLOWUP_SYSTEM_PROMPT = ""`. Expose two constants, mirroring `insight_prompt.py`.

**`FOLLOWUP_SYSTEM_PROMPT`** — outer `create_agent` system prompt:
```
You are an expert data analyst helping users explore their data.
Call generate_followup_questions exactly once. The tool reads the query results automatically.
Do not call any other tools. Stop after generate_followup_questions completes.
```

**`FOLLOWUP_INNER_PROMPT`** — template with `{question}` and `{rows_json}`, passed to the
nested `with_structured_output` call:
```
Based on the user's question and the returned data, suggest exactly 3 relevant follow-up
questions the user can run next.

User's question: {question}

Data returned (JSON rows):
{rows_json}

Guidelines:
- Each question is concise and directly executable as a new database query.
- Ground each question in the current result (e.g. after "revenue by region," suggest
  "show the monthly trend for the top region").
- Questions should drill down, compare, or extend the current result — not repeat it.
- Do not fabricate or use generic filler prompts. Return an empty list if no meaningful
  follow-up can be derived from the data.
```

**Quality gate:** `uv run ruff check .` → `uv run ruff format --check .` → `uv run pytest`
**Commit:** `feat(followup-pipeline): add FOLLOWUP_SYSTEM_PROMPT and FOLLOWUP_INNER_PROMPT`

---

## Phase 3 — Tools: `app/tools/followup_tools.py`

Mirror of `app/tools/insight_tools.py`. New file. Key differences from InsightTools:

| InsightTools | FollowupTools |
|---|---|
| `_MAX_INSIGHT_ROWS = 200` | `_MAX_FOLLOWUP_ROWS = 50` |
| `InsightOutput` | `FollowupOutput` |
| `INSIGHT_INNER_PROMPT` | `FOLLOWUP_INNER_PROMPT` |
| `update["insights"]` | `update["followup_questions"]` |
| `generate_insights` | `generate_followup_questions` |

**`_FollowupToolState(TypedDict, total=False)`** — declares only `question: str` and
`query_result: Optional[QueryResult]`. Same rationale as `_InsightToolState`: using
`WorkflowState` would trigger Pydantic validation errors because `FollowupAgentState`
is missing `WorkflowState`'s `Optional` fields that have no `= None` defaults.

**`generate_followup_questions` tool logic:**
1. Read `query_result` and `question` from injected `_FollowupToolState`.
2. If `query_result` is `None` or `rows` is empty → return `Command(update={"followup_questions": [], ...})` without LLM call.
3. Truncate to `rows[:_MAX_FOLLOWUP_ROWS]`; log a warning if rows were dropped.
4. Format `FOLLOWUP_INNER_PROMPT.format(question=question, rows_json=json.dumps(rows))`.
5. Call `llm.with_structured_output(FollowupOutput).invoke([HumanMessage(content=prompt)])`.
6. Return `Command(update={"followup_questions": result.followup_questions, "messages": [ToolMessage(...)]})`.
7. On any exception: log, return `Command(update={"followup_questions": [], ...})`; do NOT set `error_message`.

**Quality gate:** `uv run ruff check .` → `uv run ruff format --check .` → `uv run pytest`
**Commit:** `feat(followup-pipeline): add FollowupTools with generate_followup_questions`

---

## Phase 4 — Agent: `app/agents/followup_agent.py`

Replace the stub. Mirror of `app/agents/insight_agent.py`. Key differences:

| InsightAgent | FollowupAgent |
|---|---|
| `InsightAgentState` | `FollowupAgentState` |
| `state.insights` | `state.followup_questions` |
| `InsightTools` | `FollowupTools` |
| `INSIGHT_SYSTEM_PROMPT` | `FOLLOWUP_SYSTEM_PROMPT` |
| `HumanMessage("Analyze the query results.")` | `HumanMessage("Suggest follow-up questions for the query results.")` |
| `return {"insights": result.get("insights")}` | `return {"followup_questions": result.get("followup_questions")}` |

**`FollowupAgentState(MessagesState)`** — private state schema with:
- `question: str`
- `query_result: Optional[QueryResult]`
- `followup_questions: Optional[list[str]]`

**`FollowupAgent.__init__(llm)`:**
```python
followup_tools = FollowupTools(llm=llm)
self._agent = create_agent(
    model=llm,
    tools=[followup_tools.generate_followup_questions],
    system_prompt=FOLLOWUP_SYSTEM_PROMPT,
    state_schema=FollowupAgentState,
    name="followup_agent",
)
```

**`FollowupAgent.node(state: WorkflowState) -> dict`:**
```python
result = self._agent.invoke({
    "messages": [HumanMessage(content="Suggest follow-up questions for the query results.")],
    "question": state.get("question", ""),
    "query_result": state.get("query_result"),
})
return {"followup_questions": result.get("followup_questions")}
```

`graph.py` already registers `followup_agent.node` — no graph changes needed.

**Quality gate:** `uv run ruff check .` → `uv run ruff format --check .` → `uv run pytest`
**Commit:** `feat(followup-pipeline): implement FollowupAgent replacing stub`

---

## Phase 5 — Tests: `tests/agents/test_followup_agent.py`

Mirror of `tests/agents/test_insight_agent.py`. Eight test cases:

| Test | Verifies |
|---|---|
| `test_generate_followup_questions_success` | LLM returns questions; `followup_questions` written to `Command.update`; LLM called once |
| `test_generate_followup_questions_empty_rows` | `followup_questions=[]`; LLM NOT called |
| `test_generate_followup_questions_none_result` | `followup_questions=[]`; LLM NOT called |
| `test_generate_followup_questions_llm_exception` | `followup_questions=[]`; `error_message` NOT set |
| `test_generate_followup_questions_row_truncation` | With 60 rows in state, only 50 passed to LLM prompt |
| `test_followup_agent_compiles` | `agent._agent` is `CompiledStateGraph` |
| `test_followup_agent_node_invokes_agent_with_fresh_state` | `node()` passes single HumanMessage + correct fields; returns only `followup_questions` |
| `test_followup_tools_attribute_set` | `tools.generate_followup_questions` is not None |

**Row-truncation test pattern:**
```python
def test_generate_followup_questions_row_truncation():
    """Only 50 rows are serialized to the prompt when result set is larger."""
    mock_chain = MagicMock()
    mock_chain.invoke.return_value = FollowupOutput(followup_questions=["q1", "q2", "q3"])
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_chain

    tools = FollowupTools(mock_llm)
    big_result = QueryResult(
        rows=[{"region": "East", "sales": float(i)} for i in range(60)],
        columns=["region", "sales"],
        row_count=60,
    )
    tools.generate_followup_questions.func(
        tool_call_id="tc-trunc",
        state={"query_result": big_result, "question": "test", "messages": []},
    )

    import json
    call_args = mock_chain.invoke.call_args[0][0]
    prompt_text = call_args[0].content
    rows_sent = json.loads(prompt_text.split("Data returned (JSON rows):\n")[1].strip())
    assert len(rows_sent) == 50
```

**Quality gate:** `uv run ruff check .` → `uv run ruff format --check .` → `uv run pytest`
**Commit:** `test(followup-pipeline): add unit tests for FollowupAgent and FollowupTools`

---

## Phase 6 — UI: `website/app.py`

Two changes: (1) session-state initialization + submit logic for one-click re-submission;
(2) Suggested Questions rendering after the insights panel.

### 6a. Session state + submit logic

Add `pending_question` initialization after the existing `session_uuid` block:

```python
if "pending_question" not in st.session_state:
    st.session_state.pending_question = ""
```

Replace the `question = st.text_input(...)` and `submitted = st.button(...)` lines:

```python
pending = st.session_state.pending_question
auto_submit = bool(pending)
if auto_submit:
    st.session_state.pending_question = ""

question = st.text_input("Ask a question about your data", value=pending)
submitted = st.button("Submit") or auto_submit
```

Replace the `if submitted:` block's inner empty-check and every use of `question` with
`effective_question`:

```python
if submitted:
    effective_question = pending if auto_submit else question
    if not effective_question.strip():
        st.info("Please enter a question")
    else:
        with st.spinner("Analyzing..."):
            try:
                response = httpx.post(
                    ...,
                    json={
                        "session_uuid": st.session_state.session_uuid,
                        "question": effective_question,
                    },
                    ...
                )
```

### 6b. Suggested Questions rendering

After the existing insights block (after `for insight in insights: st.markdown(...)`),
add:

```python
followup_questions = data.get("followup_questions") or []
if followup_questions:
    st.subheader("Suggested Questions")
    for q in followup_questions:
        if st.button(q, key=f"followup_{hash(q)}"):
            st.session_state.pending_question = q
            st.rerun()
```

**Quality gate:** `uv run ruff check .` → `uv run ruff format --check .` → `uv run pytest`
**Commit:** `feat(streamlit-ui): add Suggested Questions section with one-click re-submission`

---

## Quality Gates (all phases)

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

Run in this order before every commit. All three must pass — no exceptions.

---

## Implementation Order Rationale

Schema → Prompts → Tools → Agent → Tests → UI follows the dependency chain: Tools import
Schema and Prompts; Agent imports Tools and Prompts; Tests import both Agent and Tools; UI
is independent but benefits from the backend being testable first. The gate after each phase
keeps failures isolated to the phase that introduced them.
