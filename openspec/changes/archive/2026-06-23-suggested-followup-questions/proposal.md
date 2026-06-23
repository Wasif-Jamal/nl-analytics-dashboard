# Proposal: suggested-followup-questions

## Summary

Implement the **FollowupAgent** (FR-10) — replacing the current pass-through stub with a
`create_agent()` instance that reads `question` and `query_result` from `WorkflowState`
and proposes exactly 3 relevant follow-up questions. Wire the Streamlit UI to render a
"Suggested Questions" section with buttons that pre-fill and re-submit the selected question.

---

## Why

The FollowupAgent is currently a stub (landed in the insights-generation change as a
placeholder). FR-10 requires one-click follow-up question suggestions after every result
to close the exploratory analysis loop. The graph wiring, state field (`followup_questions`),
and API response field are already in place — this change fills in the stub with real logic
and delivers the full end-to-end feature including the UI.

---

## Goals

- Implement `FollowupAgent` as a `create_agent()` instance with a private
  `FollowupAgentState` and a `node()` bridge method (mirrors `InsightAgent` exactly)
- Implement `FollowupTools` with a `generate_followup_questions` tool (50-row cap;
  exactly 3 questions; non-fatal on failure)
- Add `FollowupOutput` Pydantic schema in `app/schemas/followup_result.py`
- Write real `FOLLOWUP_SYSTEM_PROMPT` and `FOLLOWUP_INNER_PROMPT` in
  `app/prompts/followup_prompt.py`
- Render a "Suggested Questions" section in the Streamlit UI; each question is an
  `st.button` that pre-fills the question input and triggers re-submission

## Non-Goals

- Changing graph topology — `followup_agent` already runs in parallel after SQL Agent
  succeeds; no graph changes needed
- Modifying `WorkflowState` — `followup_questions: Optional[list[str]]` already exists
- Modifying `AnalyticsResponse` — `followup_questions: Optional[list[str]]` already exists
- Visualization Agent logic — separate issue
- Chart rendering — separate issue

---

## Design

### FollowupAgent

Class in `app/agents/followup_agent.py`, replacing the stub. Exact mirror of `InsightAgent`:

- **`FollowupAgentState`** — private `MessagesState` subclass with `question`,
  `query_result` (`Optional[QueryResult]`), and `followup_questions` (`Optional[list[str]]`)
  fields.
- **`__init__(llm)`** — instantiates `FollowupTools`, calls `create_agent()` with
  `FOLLOWUP_SYSTEM_PROMPT`, `state_schema=FollowupAgentState`, `name="followup_agent"`.
  Stores the compiled agent as `self._agent`.
- **`node(state: WorkflowState) -> dict`** — constructs a fresh `FollowupAgentState`
  (single `HumanMessage` trigger; clean context), invokes `self._agent`, returns
  `{"followup_questions": result.get("followup_questions")}`.

### FollowupTools

Class in `app/tools/followup_tools.py`. Builds one `@tool` closure in `__init__`:

**`generate_followup_questions(tool_call_id, state)`**

- Reads `query_result` and `question` via
  `Annotated[_FollowupToolState, InjectedState()]` — a minimal `TypedDict(total=False)`
  with only those two fields (same pattern as `_InsightToolState`). The LLM does not
  pass rows as arguments.
- Rows are **capped at 50** before JSON serialization — data shape and patterns
  are sufficient for question generation.
- When `query_result` is set and `rows` is non-empty: makes a nested
  `llm.with_structured_output(FollowupOutput)` call using `FOLLOWUP_INNER_PROMPT`.
  Returns `Command(update={"followup_questions": result.followup_questions, ...})`.
- When `query_result` is `None` or `rows` is empty: returns
  `Command(update={"followup_questions": [], "messages": [ToolMessage(content="No data.", ...)]})` without calling the LLM.
- On LLM failure: logs exception, returns
  `Command(update={"followup_questions": [], ...})`; does NOT set `error_message`
  (follow-up generation is non-fatal — the SQL result and insights remain valid).

### FollowupOutput Schema

New file `app/schemas/followup_result.py`:

```python
class FollowupOutput(BaseModel):
    followup_questions: list[str]  # exactly 3 relevant follow-up question strings
```

Used only as the structured-output target for the nested LLM call. The outer
`WorkflowState.followup_questions` field type (`Optional[list[str]]`) is unchanged.

### FOLLOWUP_SYSTEM_PROMPT

File `app/prompts/followup_prompt.py`. Replaces the empty placeholder.
Directs the agent to call `generate_followup_questions` once.

`FOLLOWUP_INNER_PROMPT` (formatted template with `{question}` and `{rows_json}`)
instructs the LLM to:
- Propose exactly 3 concise follow-up questions grounded in the current result
  (e.g. after "revenue by region," suggest "show the monthly trend for the top region")
- Each question must be independently executable as a new query through the normal flow
- Fabricated or generic filler prompts are not permitted — return an empty list if no
  meaningful follow-up can be derived from the data

### Streamlit UI

`website/app.py` — after the insights panel, render a "Suggested Questions" section
when `followup_questions` is non-empty:

```python
followup_questions = data.get("followup_questions") or []
if followup_questions:
    st.subheader("Suggested Questions")
    for q in followup_questions:
        if st.button(q, key=f"followup_{hash(q)}"):
            st.session_state["pending_question"] = q
            st.rerun()
```

On each page render: if `st.session_state.get("pending_question")` is set, the question
input is pre-filled with it and `pending_question` is cleared so it doesn't loop. The
normal submit flow handles the rest (no parallel path; same POST /api/chat call).

The `future-fields-ignored` spec requirement is updated: `followup_questions` is now
rendered; only `chart_config` remains parked.

---

## Files Touched

| File | Change |
|---|---|
| `app/agents/followup_agent.py` | **Update** — replace stub with `create_agent()` instance |
| `app/tools/followup_tools.py` | **New** — `FollowupTools` with `generate_followup_questions` |
| `app/prompts/followup_prompt.py` | **Update** — real `FOLLOWUP_SYSTEM_PROMPT` + `FOLLOWUP_INNER_PROMPT` |
| `app/schemas/followup_result.py` | **New** — `FollowupOutput` Pydantic schema |
| `website/app.py` | **Update** — add followup-questions-display; update future-fields-ignored |
| `tests/agents/test_followup_agent.py` | **New** — unit tests for `FollowupAgent` |

---

## Open Questions

None — all design decisions resolved during spec clarification.
