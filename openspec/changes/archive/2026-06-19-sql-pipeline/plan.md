# Implementation Plan — SQL Pipeline

## Codebase State (pre-implementation)

Already implemented — consumed, not recreated:
- `app/config/env_config.py` — `Settings` (pydantic-settings); needs `sql_retry_limit: int = 3` added
- `app/config/db_config.py` — engine + `SessionLocal` + `get_session()`
- `app/config/llm_config.py` — `get_llm()` returning `ChatGoogleGenerativeAI`
- `app/config/log_config.py` — `get_logger(__name__)`
- `app/repositories/query_repository.py` — `QueryRepository.execute_select()` currently returns `pd.DataFrame`; **must be updated to return `QueryResult`**
- `app/schemas/sql_result.py` — `SQLGenerationOutput(sql, explanation, is_identifiable)` exists; **`QueryResult` must be added**
- `app/prompts/sql_prompt.py` — `SQL_SYSTEM_PROMPT` (schema-aware, includes examples); **not modified**
- `tests/conftest.py` — `initialized_engine` fixture (isolated file-based SQLite + sample Superstore CSV); **reused by integration tests as-is**
- `tests/repositories/test_query_repository.py` — existing tests returning `pd.DataFrame`; **must be updated for `QueryResult`**

---

## Architecture Decisions

> **API verified against installed source** (`langchain 1.3.9` / `langgraph 1.2.5`):
> `create_agent(model, tools, *, system_prompt, response_format, state_schema, checkpointer, ...) -> CompiledStateGraph` (param is `system_prompt`, not `prompt`); `response_format=<Model>` ⇒ `result["structured_response"]`; step bound via `config={"recursion_limit": N}` on `.invoke()` (internal default 9999). Imports: `Command` ← `langgraph.types` (`update=`); `InjectedState` ← `langgraph.prebuilt`; `InjectedToolCallId`, `tool` ← `langchain_core.tools`; `ToolMessage` ← `langchain_core.messages` (accepts `content=`, `tool_call_id=`); `MessagesState` ← `langgraph.graph` (subclassable TypedDict).

**1. `create_agent` is `from langchain.agents import create_agent`**
This is the canonical LangChain agent builder — not a shorthand for `create_react_agent`. Both `AnalyticsGraph` (supervisor) and `SqlAgent` (inner autonomous agent) use it. Import: `from langchain.agents import create_agent`.

The outer supervisor graph is built entirely by `create_agent` — no hand-written `StateGraph`, supervisor node, `ToolNode`, or edges (SDS §7, AGENTS.md §6). `create_agent` compiles all of that internally:
```
StateGraph (built by create_agent)
  └─ supervisor node ⇄ ToolNode ─→ [ query_database ]   # issues #5–#7 append the other 3 tools
```
For issue #1 the tools list is `[query_database]`; #5–#7 append `generate_visualization`, `generate_insights`, `suggest_followups` to the same list — no structural change.

**2. `SqlAgent` is an autonomous `create_agent` agent**
`SqlAgent` does not call `llm.with_structured_output(...)` directly. It constructs its own inner `create_agent` agent with `SQL_SYSTEM_PROMPT`, a `validate_and_execute` tool, and `response_format=SQLGenerationOutput`. The inner agent's own reasoning loop handles self-correction — it calls `validate_and_execute`, receives error feedback, and retries autonomously. There is no manual for-loop retry in application code.

**3. `SQL_RETRY_LIMIT` maps to the inner agent's invocation config**
Passed as recursion/step limit when invoking the inner agent (e.g. `config={"recursion_limit": retry_limit * 2 + 1}`), bounding how many tool-call cycles it may run before the harness stops it.

**4. Result-passing is concurrency-safe via the inner agent's own state (not a shared dict)**
The compiled graph — and therefore the single `SqlAgent` instance — is reused across all FastAPI requests, which are served concurrently. A closure-captured `_captured` dict would race (two in-flight questions clobbering one dict). Instead the **inner agent gets its own state schema** (`SqlAgentState`, extending `AgentState`): `validate_and_execute` returns a `Command` writing `query_result`/`error_type` into that inner state, and `query_database` reads them from the inner agent's `invoke()` return dict. No shared mutable state.

**5. `SqlAgentState` carries the result and the error type**
`validate_and_execute` writes `query_result: QueryResult` on success and `error_type` (`"validation"` | `"database"`) on failure into the inner agent state, so `query_database` can map the two failure kinds to their distinct user-facing messages (validation ⇒ *"Generated query could not be validated."*; database ⇒ *"Unable to retrieve data at this time."*).

**6. `validate_and_execute` is the inner tool on `SqlAgent`**
It validates via `validate_select_only`, executes via `QueryService`, and returns a `Command` that updates `SqlAgentState` plus a brief `ToolMessage` the inner agent's loop reads as success/error feedback for self-correction.

**7. `WorkflowState` lives in `app/orchestration/state.py`**
SDS §5 and AGENTS.md both specify this path. The stale `.pyc` at `app/schemas/workflow_state.py` is a build artefact — do not recreate a source file there.

**8. `WorkflowState` is a `TypedDict` (`MessagesState` subclass), not Pydantic**
LangGraph's `MessagesState` is a `TypedDict`. Subclassing it yields a `TypedDict`, correct for in-process execution state. Fields typed `Optional[X]` default to `None`.

**9. `QueryResult` is a Pydantic model with `arbitrary_types_allowed`**
Holds `dataframe: pd.DataFrame`, `columns: list[str]`, `row_count: int`. Lives in `app/schemas/sql_result.py` alongside `SQLGenerationOutput`.

**10. `validate_select_only` uses `sqlglot` for AST-level parsing**
`sqlglot` is added as a project dependency (`uv add sqlglot`). It parses SQL into an AST and lets us inspect the statement type directly — no string or regex matching. This handles edge cases regex cannot: CTEs (`WITH … AS (SELECT …)` is read-only), subqueries, semicolons separating multiple statements, and case/whitespace variations. The check is: parse the SQL with the `sqlite` dialect, assert all top-level statements are `sqlglot.exp.Select`, and assert none are `DML` / `DDL` expressions.

**11. `SQL_SYSTEM_PROMPT` is already complete — not modified**
Passed as `system_prompt` to the inner `create_agent`.

**12. `ORCHESTRATOR_PROMPT` is minimal for this issue**
Only `query_database` is registered in the supervisor graph at this stage.

---

## Files

### CREATE

| File | Purpose |
|---|---|
| `app/orchestration/state.py` | `WorkflowState` TypedDict |
| `app/orchestration/graph.py` | `AnalyticsGraph` class |
| `app/agents/sql_agent.py` | `SqlAgent` class — autonomous `create_agent` + `get_tools()` |
| `app/services/sql_service.py` | `QueryService` class |
| `app/utils/validators.py` | `validate_select_only(sql: str) -> bool` |
| `app/prompts/orchestrator_prompt.py` | `ORCHESTRATOR_PROMPT` constant |
| `.env.example` | Canonical env var reference |
| `tests/agents/test_sql_agent.py` | Unit tests for `SqlAgent` tool behaviour |
| `tests/utils/test_validators.py` | Unit tests for `validate_select_only` |
| `tests/services/test_sql_service.py` | Unit tests for `QueryService` |
| `tests/orchestration/test_graph.py` | Unit tests for `AnalyticsGraph.build()` |
| `tests/workflows/test_sql_pipeline.py` | Integration tests — in-memory SQLite + mocked LLM |

### MODIFY

| File | Change |
|---|---|
| `app/config/env_config.py` | Add `sql_retry_limit: int = 3` to `Settings` |
| `app/schemas/sql_result.py` | Add `QueryResult` Pydantic model |
| `app/repositories/query_repository.py` | Update `execute_select` return type to `QueryResult` |
| `tests/repositories/test_query_repository.py` | Update assertions for `QueryResult` shape |
| `pyproject.toml` + `uv.lock` | `uv add sqlglot` — SQL parser for `validate_select_only` |

---

## Pydantic / Schema Shapes

### `app/schemas/sql_result.py` — add `QueryResult`

```python
import pandas as pd
from pydantic import BaseModel, ConfigDict

# SQLGenerationOutput already exists — not changed

class QueryResult(BaseModel):
    """Result of a successfully executed SELECT query."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    dataframe: pd.DataFrame
    columns: list[str]
    row_count: int
```

### `app/orchestration/state.py` — `WorkflowState`

```python
from typing import Optional
from langgraph.graph import MessagesState
from app.schemas.sql_result import QueryResult

class WorkflowState(MessagesState):
    # messages inherited from MessagesState (ReAct conversation history)
    question: str
    generated_sql: Optional[str]
    sql_explanation: Optional[str]
    query_result: Optional[QueryResult]
    chart_config: Optional[dict]            # placeholder; ChartConfig added in issue #5
    insights: Optional[list[str]]           # placeholder; InsightOutput added in issue #6
    followup_questions: Optional[list[str]] # placeholder; FollowupOutput added in issue #7
    error_message: Optional[str]
```

### `app/agents/sql_agent.py` — `SqlAgentState` (inner agent's own state)

```python
from typing import Optional
from langchain.agents import AgentState   # extends AgentState → gives messages + structured_response
from app.schemas.sql_result import QueryResult

class SqlAgentState(AgentState):
    query_result: Optional[QueryResult]
    error_type: Optional[str]   # "validation" | "database" | None
```
> The inner agent extends `AgentState` (not `MessagesState`) because it uses `response_format`, which writes into `AgentState.structured_response`. Confirm the public import path for `AgentState` at implementation time (see Risks).

---

## Method Signatures

### `app/utils/validators.py`

```python
def validate_select_only(sql: str) -> bool:
    """Return True if sql is a read-only SELECT; False if it contains write/DDL."""
```

Strategy: parse with `sqlglot.parse(sql, dialect="sqlite")`. Return `False` if parsing raises (malformed SQL). Iterate all top-level statements — return `False` if any statement is not a `sqlglot.exp.Select`. This correctly handles CTEs (the outer `With` wraps a `Select`, which passes), multiple statements separated by semicolons, and all case/whitespace variations without string matching.

### `app/repositories/query_repository.py` (modified)

```python
def execute_select(self, sql: str) -> QueryResult:
    """Execute a validated SELECT; return a QueryResult (dataframe, columns, row_count)."""
```

### `app/services/sql_service.py`

```python
class QueryService:
    def __init__(self, repository: QueryRepository) -> None: ...

    def run_query(self, sql: str) -> QueryResult:
        """Delegate validated SQL execution to QueryRepository."""
```

### `app/agents/sql_agent.py`

```python
class SqlAgent:
    def __init__(
        self,
        llm: ChatGoogleGenerativeAI,
        query_service: QueryService,
        retry_limit: int = 3,
    ) -> None:
        # Builds the validate_and_execute @tool closure (captures query_service)
        # and self._agent via create_agent(response_format=..., state_schema=SqlAgentState).
        ...

    def get_tools(self) -> list:
        """Return [query_database] — the @tool closure for the supervisor."""
```

**Inner agent construction (inside `__init__`):**

```python
from langchain.agents import create_agent

@tool
def validate_and_execute(
    sql: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Validate SQL is read-only and execute it; feed errors back to the agent loop."""
    if not validate_select_only(sql):
        return Command(update={
            "error_type": "validation",
            "messages": [ToolMessage(
                content="Validation failed: query contains write/DDL. "
                        "Generate a SELECT-only query.",
                tool_call_id=tool_call_id,
            )],
        })
    try:
        result = query_service.run_query(sql)
    except Exception as e:
        return Command(update={
            "error_type": "database",
            "messages": [ToolMessage(
                content=f"Execution error: {e!s}. Please correct the query.",
                tool_call_id=tool_call_id,
            )],
        })
    summary = (
        f"retrieved {result.row_count} rows. Columns: {', '.join(result.columns)}"
        if result.row_count else "Query succeeded but returned 0 rows."
    )
    return Command(update={
        "query_result": result,
        "error_type": None,
        "messages": [ToolMessage(content=summary, tool_call_id=tool_call_id)],
    })

self._agent = create_agent(
    model=llm,
    tools=[validate_and_execute],
    system_prompt=SQL_SYSTEM_PROMPT,
    response_format=SQLGenerationOutput,  # inner["structured_response"] → SQLGenerationOutput
    state_schema=SqlAgentState,
)
self._retry_limit = retry_limit
```

**`query_database` tool (returned by `get_tools`):**

```python
@tool
def query_database(
    question: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    _state: Annotated[WorkflowState, InjectedState],  # underscore: intentionally unused
) -> Command:
    """Translate a natural-language question to SQL, validate, and execute it."""
    inner = self._agent.invoke(
        {"messages": [{"role": "user", "content": question}]},
        config={"recursion_limit": self._retry_limit * 2 + 1},
    )
    output: SQLGenerationOutput = inner["structured_response"]

    if not output.is_identifiable:
        return Command(update={
            "error_message": "Unable to identify requested entities.",
            "query_result": None,
            "messages": [ToolMessage(
                content="Unable to identify requested entities.",
                tool_call_id=tool_call_id,
            )],
        })

    base_update = {
        "generated_sql": output.sql,
        "sql_explanation": output.explanation,
    }

    query_result: QueryResult | None = inner.get("query_result")
    error_type: str | None = inner.get("error_type")

    if query_result is None:
        if error_type == "database":
            error_message = "Unable to retrieve data at this time."
        else:
            error_message = "Generated query could not be validated."
        return Command(update={
            **base_update,
            "query_result": None,
            "error_message": error_message,
            "messages": [ToolMessage(
                content=error_message,
                tool_call_id=tool_call_id,
            )],
        })

    if query_result.row_count == 0:
        return Command(update={
            **base_update,
            "query_result": None,
            "error_message": "No data found for the requested query.",
            "messages": [ToolMessage(
                content="No data found for the requested query.",
                tool_call_id=tool_call_id,
            )],
        })

    summary = (
        f"retrieved {query_result.row_count} rows. "
        f"Columns: {', '.join(query_result.columns)}"
    )
    return Command(update={
        **base_update,
        "query_result": query_result,
        "error_message": None,       # clear any stale error from a prior run
        "messages": [ToolMessage(
            content=summary,
            tool_call_id=tool_call_id,
        )],
    })
```

### `app/orchestration/graph.py`

```python
from langchain.agents import create_agent

class AnalyticsGraph:
    def __init__(
        self,
        llm: ChatGoogleGenerativeAI,
        query_service: QueryService,
        retry_limit: int = 3,
    ) -> None: ...

    def build(self) -> CompiledStateGraph:
        """Assemble tools and return the compiled supervisor graph."""
        sql_agent = SqlAgent(self._llm, self._query_service, self._retry_limit)
        return create_agent(
            model=self._llm,
            tools=sql_agent.get_tools(),
            system_prompt=ORCHESTRATOR_PROMPT,
            state_schema=WorkflowState,
        )
```

---

## `.env.example`

```dotenv
# ── LLM ──────────────────────────────────────────────────────────────────────
GOOGLE_API_KEY=your-google-api-key-here
LLM_MODEL=gemini-2.0-flash
LLM_TEMPERATURE=0.0

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL=sqlite:///data/superstore.db
CSV_PATH=data/database.csv

# ── SQL Agent ─────────────────────────────────────────────────────────────────
SQL_RETRY_LIMIT=3
```

---

## Test Plan

### Unit — `tests/utils/test_validators.py`
- Returns `True` for a plain `SELECT`
- Returns `True` for a CTE (`WITH cte AS (SELECT ...) SELECT ...`) — read-only, AST root is `Select`
- Returns `False` for each blocked statement type: `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`
- Returns `False` for lowercase variants (e.g. `insert into ...`)
- Returns `False` for multiple semicolon-separated statements where any is non-SELECT
- Returns `False` for malformed/unparseable SQL

### Unit — `tests/repositories/test_query_repository.py` (updated)
- Existing 3 tests updated: assert return is `QueryResult`; check `row_count`, `columns`, `dataframe` shape

### Unit — `tests/services/test_sql_service.py`
- Mock `QueryRepository`; assert `QueryService.run_query` delegates and returns `QueryResult`

### Unit — `tests/agents/test_sql_agent.py`
Mock `self._agent.invoke` to return controlled inner-state dicts (`structured_response` + `query_result` + `error_type`):
- Unknown entities (`is_identifiable=False`) → `error_message = "Unable to identify requested entities."`, `query_result=None`
- Inner returns a `query_result` → `query_result` in state, ToolMessage matches template, `error_message=None`
- Inner `error_type == "validation"`, no result → `error_message = "Generated query could not be validated."`, `query_result=None`
- Inner `error_type == "database"`, no result → `error_message = "Unable to retrieve data at this time."`, `query_result=None`
- `row_count == 0` → `error_message = "No data found for the requested query."`, `query_result=None`
- `generated_sql` and `sql_explanation` written in both success and execution-failure paths

### Unit — `tests/orchestration/test_graph.py`
- `AnalyticsGraph.build()` returns a compiled graph object
- Compiled graph includes `query_database` in its tool list

### Integration — `tests/workflows/test_sql_pipeline.py`
Uses `initialized_engine` from `conftest.py`. Mocks the inner agent's `validate_and_execute` tool:
- **Happy path**: NL question → `query_result` populated, `generated_sql` written, ToolMessage matches template, `error_message=None`
- **Unknown entities**: mock `is_identifiable=False` → `error_message` set, `query_result=None`, no DB call
- **Execution retry**: first call raises (bad column); second call succeeds → result in state
- **Read-only guard**: mock returns `DELETE` → validation blocks, `error_message = "Generated query could not be validated."`
- **Database error**: `run_query` raises → `error_message = "Unable to retrieve data at this time."`
- **Empty result**: SQL matches no rows → `error_message = "No data found for the requested query."`, `query_result=None`

---

## Build Order

1. `uv add sqlglot` — add SQL parser dependency
2. `app/schemas/sql_result.py` — add `QueryResult` *(no new deps)*
3. `app/orchestration/state.py` — `WorkflowState` *(depends on `QueryResult`)*
4. `app/utils/validators.py` — `validate_select_only` *(depends on `sqlglot`)*
5. `app/config/env_config.py` — add `sql_retry_limit` *(no deps)*
6. `app/repositories/query_repository.py` — update return type to `QueryResult`
7. `app/services/sql_service.py` — `QueryService` *(depends on `QueryRepository`, `QueryResult`)*
8. `app/prompts/orchestrator_prompt.py` — `ORCHESTRATOR_PROMPT` *(no deps)*
9. `app/agents/sql_agent.py` — `SqlAgent` *(depends on 3, 4, 6, 7)*
10. `app/orchestration/graph.py` — `AnalyticsGraph` *(depends on 3, 8, 9)*
11. `.env.example` *(no deps)*
12. Tests — written alongside each unit; integration tests after step 10

---

## Risks / Verify at Implementation Time — RESOLVED

- **`state_schema` base class for the supervisor.** ✅ Resolved: `create_agent` accepts `WorkflowState` (a `MessagesState` subclass) directly — smoke-verified the graph compiles with topology `__start__→model→tools→__end__`. No `AgentState` fallback needed for the supervisor.
- **`AgentState` import path** for `SqlAgentState`. ✅ Resolved: `from langchain.agents import AgentState` works (public re-export).
- **`run_query` raising.** ✅ Implemented as planned: `QueryRepository.execute_select` lets SQLAlchemy errors propagate; the inner `validate_and_execute` catches them to set `error_type="database"`. Repository stays free of business logic.

## Deviations from plan during implementation

- Repository-test update (task 4.2) and the incidental `tests/utils/test_database_initializer.py` caller fix were pulled forward into Phase 2, because changing `execute_select`'s return type to `QueryResult` broke those callers immediately — fixing them in the same phase kept the suite green.

---

## Quality Gates

Run in order before any commit:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

All three must pass — do not commit on red.
