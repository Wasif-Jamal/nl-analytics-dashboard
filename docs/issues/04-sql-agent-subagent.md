## Requirement

Refactor `SqlAgent` from a nested inner `create_agent` loop (hidden inside a `query_database` tool) to a proper `create_agent()` instance with explicit internal tools: `generate_sql`, `validate_sql`, `execute_sql`. Establish this as the **canonical pattern for all agents** in the system. Source: architecture pivot agreed in `fix/architecture-pivot`; `docs/decisions/technical_architecture.md` §17.

> The supervisor invokes the SQL Agent as a **subagent** — not via a `query_database` tool. The SQL Agent is its own `create_agent()` instance; its internal tools are invisible to the supervisor.

---

## Motivation

The current `SqlAgent` wraps a second `create_agent` inside a `query_database` tool that the supervisor calls. Problems:

- Two hidden ReAct loops — the supervisor's loop and the inner agent's loop — with no visibility into which step failed
- `query_database` is a single atomic tool from the supervisor's perspective; there are no observable steps
- The Visualization Agent is a deterministic function with no LLM, limiting its adaptability
- All agents should follow a single consistent pattern

Moving every agent to a `create_agent()` instance with explicit tools gives:

- **One loop per agent** — the agent's own LLM drives the tool-calling loop; no nesting
- **Explicit, testable tools** — `generate_sql`, `validate_sql`, `execute_sql` are callable independently in tests
- **Consistent pattern** — `VisualizationAgent`, `InsightAgent`, `FollowupAgent` follow the same shape
- **LLM-driven adaptability** — every agent (including Visualization) uses its own LLM to decide which tools to call

---

## Acceptance Criteria

All existing acceptance criteria from issue #1 continue to hold. Additionally:

1. `SqlAgent` is a `create_agent()` instance — not a wrapper around a nested `create_agent`.
2. The SQL Agent has three internal tools: `generate_sql`, `validate_sql`, `execute_sql`.
3. `generate_sql` — produces a `SQLGenerationOutput` (sql, explanation, is_identifiable); includes retry context on subsequent attempts.
4. `validate_sql` — calls `validate_select_only(sql)` from `app/utils/validators.py`; blocks non-SELECT SQL.
5. `execute_sql` — calls `POST /api/query` via `httpx`; returns a `QueryResult` on success or signals an error type for retry.
6. The SQL Agent's own LLM drives the generate → validate → execute → retry loop via `create_agent`'s ReAct mechanism.
7. There is no `query_database` tool — the supervisor invokes the SQL Agent directly as a subagent.
8. `AnalyticsGraph` updated to route to the SQL Agent subagent (not a flat tool list).
9. Error messages (unidentifiable question, validation failure, empty result, DB error) are surfaced from the SQL Agent to `WorkflowState` unchanged.
10. All existing tests pass. New tool-level unit tests added for `generate_sql`, `validate_sql`, and `execute_sql`.

---

## Agent Pattern (applies to all agents)

Every agent in this codebase follows this structure:

```python
class XAgent:
    def __init__(self, llm, ...):
        self._tools = self._build_tools(...)
        self._agent = create_agent(
            model=llm,
            tools=self._tools,
            system_prompt=X_SYSTEM_PROMPT,
            state_schema=XAgentState,
        )

    def _build_tools(self, ...) -> list[BaseTool]:
        @tool
        def tool_a(...) -> ...:
            """Tool description."""
            ...

        @tool
        def tool_b(...) -> ...:
            """Tool description."""
            ...

        return [tool_a, tool_b]
```

All four agents follow this pattern. Each agent uses its own LLM to decide which tools to call and in what order. The supervisor invokes each agent as a subagent; agent-internal tools are not visible to the supervisor.

---

## Architecture Scope

| Component | Path | Change |
|---|---|---|
| `SqlAgent` | `app/agents/sql_agent.py` | Major rewrite — remove nested inner agent + `query_database` tool; add `create_agent()` with `generate_sql`, `validate_sql`, `execute_sql` |
| `SqlAgentState` | `app/agents/sql_agent.py` | Private `MessagesState` subclass (or `TypedDict`) for the agent's own state |
| `AnalyticsGraph` | `app/orchestration/graph.py` | Updated to route to SQL Agent as a subagent (not `tools=[query_database]`) |
| `test_sql_agent.py` | `tests/agents/test_sql_agent.py` | Mock `agent._agent`; add tool-level tests for `generate_sql`, `validate_sql`, `execute_sql` |
| `test_sql_pipeline.py` | `tests/workflows/test_sql_pipeline.py` | Update to drive the SQL Agent subagent directly rather than calling `query_database` |

---

## Implementation Tasks

### Task 1 — Define `SqlAgentState`

**File:** `app/agents/sql_agent.py`

The SQL Agent uses its own private state — separate from `WorkflowState`.

```python
from langgraph.graph import MessagesState

class SqlAgentState(MessagesState):
    """Private state for the SQL Agent's create_agent() loop."""
    question: str
    generated_sql: str | None
    sql_explanation: str | None
    query_result: QueryResult | None
    error_type: str | None   # "validation" | "database" | None
```

---

### Task 2 — Build `generate_sql` tool

**File:** `app/agents/sql_agent.py`

The SQL Agent's LLM calls this tool to produce a structured SQL generation output.

```python
from app.prompts.sql_prompt import SQL_SYSTEM_PROMPT
from app.schemas.sql_result import SQLGenerationOutput

@tool
def generate_sql(question: str) -> SQLGenerationOutput:
    """Generate a SELECT SQL query for the given natural-language question.

    Returns SQLGenerationOutput with sql, explanation, and is_identifiable.
    """
    llm_with_output = llm.with_structured_output(SQLGenerationOutput)
    return llm_with_output.invoke([
        SystemMessage(SQL_SYSTEM_PROMPT),
        HumanMessage(question),
    ])
```

---

### Task 3 — Build `validate_sql` tool

**File:** `app/agents/sql_agent.py`

```python
from app.utils.validators import validate_select_only

@tool
def validate_sql(sql: str) -> dict:
    """Validate that the SQL is a read-only SELECT statement.

    Returns {"valid": True} or {"valid": False, "reason": "..."}.
    """
    if validate_select_only(sql):
        logger.debug("validate_sql passed: %s", sql[:200])
        return {"valid": True}
    logger.warning("validate_sql failed: %s", sql[:200])
    return {"valid": False, "reason": "Only SELECT statements are permitted."}
```

---

### Task 4 — Build `execute_sql` tool

**File:** `app/agents/sql_agent.py`

```python
import httpx
import pandas as pd
from app.schemas.sql_result import QueryResult

@tool
def execute_sql(sql: str) -> dict:
    """Execute a validated SELECT SQL query via POST /api/query.

    Returns {"query_result": QueryResult} on success or {"error": "..."} on failure.
    """
    try:
        with httpx.Client() as client:
            response = client.post(
                f"{api_base_url}/api/query",
                json={"sql": sql},
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
        result = QueryResult(
            dataframe=pd.DataFrame(data["rows"]),
            columns=data["columns"],
            row_count=data["row_count"],
        )
        logger.info("execute_sql: %d row(s), columns=%s", result.row_count, result.columns)
        return {"query_result": result}
    except Exception as exc:  # noqa: BLE001
        logger.warning("execute_sql failed: %s", exc)
        return {"error": str(exc)}
```

---

### Task 5 — Rewrite `SqlAgent.__init__` with `create_agent()`

**File:** `app/agents/sql_agent.py`

```python
from langgraph.prebuilt import create_agent
from app.prompts.sql_prompt import SQL_SYSTEM_PROMPT

class SqlAgent:
    """SQL generation and execution subagent.

    A create_agent() instance with internal tools: generate_sql, validate_sql,
    execute_sql. Invoked by the supervisor as a subagent; internal tools are
    invisible to the supervisor. Only agent permitted to read from the database.
    """

    def __init__(
        self,
        llm: ChatGoogleGenerativeAI,
        api_base_url: str | None = None,
        retry_limit: int | None = None,
    ) -> None:
        self._api_base_url = api_base_url or settings.api_base_url
        self._retry_limit = (
            retry_limit if retry_limit is not None else settings.sql_retry_limit
        )
        logger.info("SqlAgent initializing (api_base_url=%s)", self._api_base_url)
        tools = self._build_tools()
        self._agent = create_agent(
            model=llm,
            tools=tools,
            system_prompt=SQL_SYSTEM_PROMPT,
            state_schema=SqlAgentState,
        )

    def _build_tools(self) -> list[BaseTool]:
        """Build internal tools: generate_sql, validate_sql, execute_sql."""
        api_base_url = self._api_base_url
        # define and return [generate_sql, validate_sql, execute_sql] closures
        ...
```

---

### Task 6 — Update `AnalyticsGraph` to invoke SQL Agent as subagent

**File:** `app/orchestration/graph.py`

Remove `SqlAgent.get_tools()` and `create_agent(tools=[query_database], ...)`. Instead, register the SQL Agent's compiled graph as a subagent node in the supervisor graph.

```python
from app.agents.sql_agent import SqlAgent

class AnalyticsGraph:
    def build(self) -> CompiledStateGraph:
        sql_agent = SqlAgent(self._llm).build()  # returns compiled agent graph
        # wire sql_agent as a node/subagent in the supervisor graph
        ...
```

---

### Task 7 — Update unit tests (`test_sql_agent.py`)

**File:** `tests/agents/test_sql_agent.py`

Mock `agent._agent` for end-to-end tool flow tests. Add direct tool-level tests for `generate_sql`, `validate_sql`, and `execute_sql` by calling them with mocked dependencies.

```python
def test_validate_sql_passes_select():
    # call validate_sql tool directly with a SELECT statement
    result = validate_sql.func("SELECT 1")
    assert result["valid"] is True

def test_validate_sql_blocks_delete():
    result = validate_sql.func("DELETE FROM orders")
    assert result["valid"] is False

def test_execute_sql_calls_api_and_returns_result():
    # patch httpx.Client, assert query_result is populated
    ...
```

---

### Task 8 — Update integration tests (`test_sql_pipeline.py`)

**File:** `tests/workflows/test_sql_pipeline.py`

Drive the SQL Agent subagent directly. Mock the agent's internal LLM decisions and use `_QueryServiceTransport` for the `POST /api/query` calls.

---

## Future Agent Pattern (Issues #6, #7, #8)

All four agents follow the same `create_agent()` pattern:

| Agent | Internal tools | Notes |
|---|---|---|
| `SqlAgent` | `generate_sql`, `validate_sql`, `execute_sql` | Only agent with database access (via `execute_sql`) |
| `VisualizationAgent` | chart selection + config tools | LLM-driven; reads `query_result` from state |
| `InsightAgent` | data analysis tools | Data-grounded LLM call; no fabrication permitted |
| `FollowupAgent` | question generation tools | LLM call over question + result |

Every agent: one class, one `create_agent()` instance, own tools. No nested agents anywhere.

---

## Out of Scope

- Visualization, Insight, Follow-up agent implementation (issues #6, #7, #8).
- Streaming or async agent invocation.
- Changes to `WorkflowState` schema — state fields are unchanged.
