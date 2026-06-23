# Tasks: insights-generation

Sequenced from `plan.md`. Phases match the plan's dependency order.
Quality gate runs after each phase — all three commands must be green before
moving to the next phase.

```bash
# Quality gate (run after every phase)
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## Phase 1 — Foundation (schemas + prompts)

No dependencies. All tasks in this phase are independent (PARALLEL).

- [ ] **T1** Create `app/schemas/insight_result.py`
  - `InsightOutput(BaseModel)` with `insights: list[str]`
  - Module docstring; class docstring naming the contract

- [ ] **T2** Create `app/prompts/insight_prompt.py`
  - `INSIGHT_SYSTEM_PROMPT` — outer `create_agent` system prompt (one-shot: call `generate_insights` once)
  - `INSIGHT_INNER_PROMPT` — inner prompt template with `{question}` and `{rows_json}` placeholders

- [ ] **T3** Create `app/prompts/visualization_prompt.py` (placeholder)
  - `VISUALIZATION_SYSTEM_PROMPT = ""`
  - Module docstring noting it will be filled in when the Visualization Agent is implemented

- [ ] **T4** Create `app/prompts/followup_prompt.py` (placeholder)
  - `FOLLOWUP_SYSTEM_PROMPT = ""`
  - Module docstring noting it will be filled in when the Follow-Up Agent is implemented

### ✅ Phase 1 checkpoint
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## Phase 2 — Core Implementation

### 2a — Tools and Agents (PARALLEL within sub-group)

- [ ] **T5** Create `app/tools/insight_tools.py`
  - `InsightTools` class; injects `llm` via constructor
  - `generate_insights` `@tool` closure stored as `self.generate_insights`
    - Params: `tool_call_id: Annotated[str, InjectedToolCallId]`, `state: Annotated[WorkflowState, InjectedState()]`
    - Happy path: `json.dumps(query_result.rows)` → `llm.with_structured_output(InsightOutput)` → `Command(update={"insights": result.insights, "messages": [...]})`
    - Empty/`None` `query_result`: return `Command(update={"insights": [], ...})` — no LLM call
    - LLM exception: log warning, return `Command(update={"insights": [], ...})` — **do not set `error_message`**
  - Module docstring; class docstring naming `InsightOutput` contract

- [ ] **T6** Create `app/agents/insight_agent.py`
  - `InsightAgent` class; injects `llm`
  - Instantiates `InsightTools(llm=llm)` in `__init__`
  - Calls `create_agent(model=llm, tools=[insight_tools.generate_insights], system_prompt=INSIGHT_SYSTEM_PROMPT, state_schema=WorkflowState, name="insight_agent")` → `self._agent`
  - Log `InsightAgent initializing` / `InsightAgent compiled`

- [ ] **T7** Create `app/agents/visualization_agent.py` (stub)
  - `VisualizationAgent` class; accepts `llm` in constructor (no-op)
  - `node(self, state: WorkflowState) -> dict` returns `{}`
  - Log `VisualizationAgent (stub) initialized` at init; `debug` log in `node()`

- [ ] **T8** Create `app/agents/followup_agent.py` (stub)
  - `FollowupAgent` class; accepts `llm` in constructor (no-op)
  - `node(self, state: WorkflowState) -> dict` returns `{}`
  - Log `FollowupAgent (stub) initialized` at init; `debug` log in `node()`

### ✅ Phase 2a checkpoint
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## Phase 3 — Integration

### 3a — Graph wiring

- [ ] **T9** Update `app/orchestration/graph.py`
  - Add imports: `VisualizationAgent`, `InsightAgent`, `FollowupAgent`
  - Add module-level routing function `_route_after_sql(state: WorkflowState) -> str | list[str]`:
    - Returns `END` when `state.get("error_message")` is truthy
    - Returns `["visualization_agent", "insight_agent", "followup_agent"]` otherwise
  - Update `build()`:
    - Construct `viz_agent = VisualizationAgent(self._llm)`, `insight_agent = InsightAgent(self._llm)`, `followup_agent = FollowupAgent(self._llm)`
    - `builder.add_node("visualization_agent", viz_agent.node)`
    - `builder.add_node("insight_agent", insight_agent._agent)`
    - `builder.add_node("followup_agent", followup_agent.node)`
    - Replace `builder.add_edge("sql_agent", END)` with `builder.add_conditional_edges("sql_agent", _route_after_sql)`
    - Add `builder.add_edge("visualization_agent", END)`, `builder.add_edge("insight_agent", END)`, `builder.add_edge("followup_agent", END)`
  - Update module docstring to reflect new topology

### 3b — Streamlit UI (PARALLEL with 3a)

- [ ] **T10** Update `website/app.py`
  - After the `if query_result:` block, add insights panel inside the `else` (no-error) branch:
    ```python
    insights = data.get("insights") or []
    if insights:
        st.subheader("Insights")
        for insight in insights:
            st.markdown(f"- {insight}")
    ```
  - No other UI changes; `followup_questions` and `chart_config` remain ignored

### ✅ Phase 3 checkpoint
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## Phase 4 — Tests

### 4a — InsightAgent / InsightTools unit tests (new file)

- [ ] **T11** Create `tests/agents/test_insight_agent.py`

  One test per spec scenario from `spec.md`:

  | Test name | Spec scenario |
  |---|---|
  | `test_generate_insights_success` | `query_result` present → LLM called → `insights` list written to `Command.update` |
  | `test_generate_insights_empty_rows` | `query_result.rows == []` → no LLM call → `insights=[]` in update |
  | `test_generate_insights_none_result` | `query_result is None` → no LLM call → `insights=[]` in update |
  | `test_generate_insights_llm_exception` | LLM raises → `insights=[]`; `"error_message"` NOT in `Command.update` (or is `None`) |
  | `test_insight_agent_compiles` | `InsightAgent(llm)._agent` is a `CompiledStateGraph` |
  | `test_insight_tools_attribute_set` | `InsightTools(llm).generate_insights` is not `None` |

  **Tool call pattern** — call `.func` directly, passing state as a dict:
  ```python
  command = tools.generate_insights.func(
      tool_call_id="tc1",
      state={"query_result": _QUERY_RESULT, "question": "Show sales by region", "messages": []},
  )
  ```

  **LLM mock pattern** (reuse from `test_sql_agent.py`):
  ```python
  mock_chain = MagicMock()
  mock_chain.invoke.return_value = InsightOutput(insights=["East leads revenue."])
  mock_llm = MagicMock()
  mock_llm.with_structured_output.return_value = mock_chain
  ```

### 4b — Graph topology tests (update existing file)

- [ ] **T12** Update `tests/orchestration/test_graph.py`
  - Update `test_build_returns_compiled_graph`: assert 5 nodes
    `{"__start__", "sql_agent", "visualization_agent", "insight_agent", "followup_agent"}`
  - Add `test_sql_error_routes_to_end`: import `_route_after_sql`; state with `error_message` set → returns `END`
  - Add `test_sql_success_fans_out`: state with `error_message=None` → returns a collection containing all three analysis node names
  - Update `test_sql_agent_is_registered_as_subgraph`: still valid (sql_agent is still a subgraph)

### ✅ Phase 4 checkpoint (final gate)
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

All tests green → ready for commit.

---

## Commit Plan

Per project convention (`feedback_commit_per_task_group.md`): one commit per
completed phase group after gates pass.

**Commit 1** (Tasks T1–T9, T11–T12 — backend):
```
feat(insight-agent): add InsightAgent, stubs, and parallel graph fan-out
```

**Commit 2** (Task T10 — UI):
```
feat(ui): add insights panel to Streamlit dashboard
```
