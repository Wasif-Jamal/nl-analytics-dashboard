## Why

The current `SqlAgent` hides a second `create_agent` loop inside a `query_database` tool
that the supervisor calls as a flat capability. This creates two invisible ReAct loops
with no observable intermediate steps, couples all SQL logic into a single opaque tool
call, and diverges from the target supervisor-over-subagents architecture that issues
#6–#8 depend on.

This change refactors `SqlAgent` into a proper `create_agent()` subagent with four
explicit internal tools (`generate_sql`, `validate_sql`, `execute_sql`,
`handle_unidentifiable`) and replaces the flat-tool supervisor with
`create_supervisor([sql_agent._agent])`. It establishes the canonical agent pattern for
all four agents in the system.

## What Changes

- **`app/tools/sql_tools.py`** — new `SqlTools` class; four `@tool` closures built as
  instance attributes in `__init__`: `generate_sql` (nested LLM call with structured
  output), `validate_sql` (read-only guard), `execute_sql` (terminal execution + state
  write), `handle_unidentifiable` (terminal error write for unrecognised questions).
- **`app/agents/sql_agent.py`** — major rewrite; remove `SqlAgentState`, `get_tools()`,
  `_build_validate_and_execute()`; instantiate `SqlTools` and pass tools directly to
  `create_agent(model, tools=[...], state_schema=WorkflowState, name="sql_agent")`;
  expose compiled agent as `self._agent`.
- **`app/orchestration/graph.py`** — replace `create_agent(tools=sql_agent.get_tools())`
  with `create_supervisor([sql_agent._agent], model=llm, prompt=ORCHESTRATOR_PROMPT, state_schema=WorkflowState).compile()`.
- **`app/prompts/orchestrator_prompt.py`** — update prompt; remove `query_database`
  reference; instruct supervisor to transfer to `sql_agent`.
- **`app/prompts/sql_prompt.py`** — update prompt; replace `validate_and_execute`
  references with the four new tool names and their roles.
- **`tests/agents/test_sql_agent.py`** — rewrite; direct tool-level tests; mock
  `llm.with_structured_output` for `generate_sql`; call `validate_sql.func`,
  `execute_sql.func`, `handle_unidentifiable.func` directly; mock `httpx.Client`.
- **`tests/workflows/test_sql_pipeline.py`** — update; drive new `SqlAgent` via
  `_agent.invoke`; retain real SQLite via `_QueryServiceTransport`.
- **`tests/orchestration/test_graph.py`** — update; assert `sql_agent` registered as
  subagent node; assert no `query_database` tool in supervisor registry.

## Capabilities

### New Capabilities

<!-- None — sql-pipeline capability already exists; no new top-level capability added. -->

### Modified Capabilities

- `sql-pipeline`: Refactored internal agent pattern. Tool chain changes from a single
  `query_database` tool to four explicit tools (`generate_sql`, `validate_sql`,
  `execute_sql`, `handle_unidentifiable`). Supervisor changes from
  `create_agent(tools=[query_database])` to `create_supervisor([sql_agent._agent])`.
  All existing scenarios (NL→SQL, read-only validation, retry, execution, error messages)
  are preserved with the same user-facing behaviour.

## Impact

- `app/tools/` directory created with `sql_tools.py`.
- `app/agents/sql_agent.py` is a breaking rewrite; `SqlAgentState` and `get_tools()` are
  removed; `self._agent` replaces them.
- `app/orchestration/graph.py` changes supervisor construction; `AnalyticsGraph.build()`
  return type is unchanged (`CompiledStateGraph`).
- All test files covering the SQL pipeline are rewritten; existing test helpers
  (`_QueryServiceTransport`, `initialized_engine` fixture) are retained.
- `langgraph-supervisor` added as a production dependency.
- Unchanged: `app/orchestration/state.py`, `app/schemas/`, `app/utils/validators.py`,
  `app/repositories/`, `app/services/`, `app/models/`, `app/routes/`, `website/app.py`.
