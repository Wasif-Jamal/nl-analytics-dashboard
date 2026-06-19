## Requirement

Business users submit a plain-English question; the system generates the corresponding SQL, validates it as read-only, executes it against the database, and returns the result as a structured payload. Source: FRS §6.1, §6.2; FR-1, FR-2, FR-3, FR-4.

> Implemented as the `query_database` tool exposed by `SqlAgent.get_tools()` and executed by `ToolNode` inside the `create_agent` supervisor. Generation, validation, and execution are a single atomic tool call with an internal self-correction retry loop.

## Acceptance Criteria

1. A plain-English question produces the corresponding `SELECT` query targeting the known schema (customers, products, orders, order_items).
2. Generated SQL is validated as read-only before execution — `SELECT` only; `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE` are blocked.
3. Validation failure prevents execution entirely (the query never reaches the database).
4. A valid query executes against the SQLite database and returns rows as a structured result (`query_result` in `WorkflowState`).
5. The generated SQL and a plain-English explanation are written to `generated_sql` and `sql_explanation` in `WorkflowState`.
6. On LLM or validation error the tool retries up to a configurable limit, feeding the error back to the LLM before surfacing a user-facing error message.
7. Execution is read-only and uses managed database sessions (via `QueryRepository`).
8. The `query_database` tool is the **only** component permitted to read from the database.

## Error Scenarios

| Trigger | Expected result |
|---|---|
| Question references entities not in the schema ("Show dragon sales by galaxy") | `Unable to identify requested entities.` — no SQL generated or executed |
| Generated SQL contains a write/DDL statement (INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE) | `Generated query could not be validated.` — execution blocked |
| SQL cannot be parsed or validated after all retries | `Generated query could not be validated.` |
| Query executes successfully but returns zero rows | `No data found for the requested query.` |
| Database is unreachable or raises a runtime error | `Unable to retrieve data at this time.` |

## Architecture Scope

This issue delivers the complete SQL pipeline and the graph it runs in:

| Component | Path | Role |
|---|---|---|
| `WorkflowState` | `app/schemas/workflow_state.py` | `MessagesState` subclass — adds `question`, `generated_sql`, `sql_explanation`, `query_result`, `error_message` |
| `SqlAgent` | `app/agents/sql_agent.py` | Class exposing `get_tools() → [query_database]`; LLM + repository injected via constructor |
| `AnalyticsGraph` | `app/orchestration/graph.py` | `build()` returns `create_agent(model, tools=[query_database], system_prompt=..., state_schema=WorkflowState)` |
| `validate_select_only` | `app/utils/validators.py` | Read-only guard used inside the tool |

The graph in this issue is intentionally configured with **only** the `query_database` tool. Visualization, insight, and follow-up tools are added in later issues (#5, #6, #7). `create_agent` accepts any tool list, so extending it requires no structural change.

## Implementation Notes

- `SqlAgent` class in `app/agents/sql_agent.py` — exposes `get_tools()` returning `[query_database]`.
- The `query_database` tool is a `@tool`-decorated closure that captures the injected `SqlAgent` and `QueryRepository` dependencies.
- SQL generation uses `llm.with_structured_output(SQLGenerationOutput)` against `SQL_SYSTEM_PROMPT` from `app/prompts/sql_prompt.py`.
- Read-only validation lives in `app/utils/validators.py` (`validate_select_only(sql) -> bool`).
- Execution goes through `QueryRepository.execute_select(sql) -> pd.DataFrame`.
- Tool returns a `Command(update={...})` with `InjectedToolCallId` — a brief `ToolMessage` summary, never the full result set.
- Reused: `SQL_SYSTEM_PROMPT` (`app/prompts/sql_prompt.py`), `SQLGenerationOutput` (`app/schemas/sql_result.py`), `QueryRepository` (`app/repositories/query_repository.py`).

## Out of Scope

- Visualization, insights, and follow-up generation (separate tools — issues #5, #6, #7).
- FastAPI / Chat Service wiring (issue #2).
- Streamlit UI (issue #3).
- Authentication / authorization (FRS §13 — out of scope for the product).
