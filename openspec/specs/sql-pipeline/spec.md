# sql-pipeline Specification

## Purpose
TBD - created by archiving change sql-pipeline. Update Purpose after archive.
## Requirements
### Requirement: natural-language-to-sql
A plain-English question submitted to the system SHALL be converted into a valid `SELECT` query targeting the known schema (customers, products, orders, order_items) using an LLM with structured output (`SQLGenerationOutput`).

#### Scenario: question maps to known entities
- **WHEN** a user submits a question referencing entities present in the schema (e.g. "Show monthly sales by category")
- **THEN** the system generates a valid `SELECT` query and writes it to `generated_sql` in `WorkflowState`, along with a plain-English explanation in `sql_explanation`

#### Scenario: question references unknown entities
- **WHEN** a user submits a question referencing entities not in the schema (e.g. "Show dragon sales by galaxy")
- **THEN** the tool shall not execute any query and `error_message` is set to `Unable to identify requested entities.`

#### Scenario: generated SQL is recorded
- **WHEN** `generate_sql` successfully produces SQL
- **THEN** `generated_sql` and `sql_explanation` are written to `WorkflowState` before execution occurs

---

### Requirement: read-only-validation
All generated SQL SHALL be validated as read-only before execution. Only `SELECT` statements are permitted; `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, and `TRUNCATE` are blocked unconditionally.

#### Scenario: valid SELECT query
- **WHEN** the generated SQL is a `SELECT` statement
- **THEN** validation passes and execution proceeds

#### Scenario: write or DDL statement generated
- **WHEN** the generated SQL contains `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, or `TRUNCATE`
- **THEN** execution is blocked entirely and `error_message` is set to `Generated query could not be validated.`

---

### Requirement: sql-self-correction-retry
On SQL generation failure, SQL validation failure, or SQL execution failure caused by an invalid generated query (e.g. referencing a non-existent column), the tool SHALL feed the error back to the LLM and retry up to `SQL_RETRY_LIMIT` times (env var, default `3`) before surfacing a user-facing error.

#### Scenario: validation fails then succeeds within retry limit
- **WHEN** the first generated SQL fails validation but a subsequent attempt within the retry limit produces a valid `SELECT`
- **THEN** the valid query is executed and results are written to `WorkflowState`

#### Scenario: execution fails due to bad SQL then succeeds within retry limit
- **WHEN** a generated SQL passes validation but fails at execution (e.g. `SELECT revenue_amount FROM orders` where `revenue_amount` does not exist) and a subsequent attempt within the retry limit produces a working query
- **THEN** the corrected query is executed and results are written to `WorkflowState`

#### Scenario: all retries exhausted
- **WHEN** every attempt within the retry limit fails generation, validation, or execution
- **THEN** `error_message` is set to `Generated query could not be validated.` and no execution occurs

---

### Requirement: sql-execution
A validated `SELECT` query SHALL be executed against the SQLite database through `QueryService`, which delegates to `QueryRepository`. The result SHALL be stored as a `QueryResult` object in `query_result` within `WorkflowState`.

`QueryResult` contains:
- `dataframe` — the raw `pd.DataFrame` returned by the database
- `columns` — list of column names
- `row_count` — number of rows returned

#### Scenario: query returns rows
- **WHEN** the validated SQL executes successfully and returns one or more rows
- **THEN** `query_result` is set to a `QueryResult` object containing `dataframe`, `columns`, and `row_count` in `WorkflowState`

#### Scenario: query returns zero rows
- **WHEN** the validated SQL executes successfully but returns no rows
- **THEN** `error_message` is set to `No data found for the requested query.`

#### Scenario: database error
- **WHEN** the database raises a runtime error during execution
- **THEN** `error_message` is set to `Unable to retrieve data at this time.`

---

### Requirement: database-access-boundary
`QueryRepository` SHALL only be invoked through `QueryService` via the `execute_sql` tool. The enforced call chain is:

```
execute_sql → POST /api/query → QueryService → QueryRepository → SQLite
```

No agent, route, or other service may invoke `QueryRepository` directly.

#### Scenario: execute_sql executes a query
- **WHEN** `execute_sql` calls `POST /api/query`, which routes to `QueryService`, which delegates to `QueryRepository.execute_select(sql)`
- **THEN** the repository manages the SQLAlchemy session, executes the query, and returns a `QueryResult` Pydantic wrapper; no component outside this chain touches the database

---

### Requirement: tool-message-summary
The `execute_sql` tool SHALL return a `Command(update={...})` with a brief, fixed-template `ToolMessage` summary. The summary MUST NOT contain the full result set.

#### Scenario: successful execution
- **WHEN** `execute_sql` succeeds
- **THEN** the `ToolMessage` content follows the template: `"retrieved {row_count} rows. Columns: {col1}, {col2}, …"` and the full result lives in `query_result` state only

---

### Requirement: workflow-state
`WorkflowState` SHALL subclass `MessagesState` and SHALL expose all of the following fields:

- `messages` (inherited from `MessagesState` — the ReAct conversation history)
- `question`
- `generated_sql`
- `sql_explanation`
- `query_result`
- `chart_config`
- `insights`
- `followup_questions`
- `error_message`

It is an in-process execution state; `query_result` holds a `QueryResult` object (containing a `pd.DataFrame`) and is not required to be JSON-serializable.

#### Scenario: state initialised for a new question
- **WHEN** the graph is invoked with a user question
- **THEN** `question` is set and all other analytics fields start as `None` / empty

---

### Requirement: env-configuration
All tuneable runtime values SHALL be sourced from environment variables defined in `app/config/env_config.py` and documented in `.env.example`. This issue introduces `SQL_RETRY_LIMIT` (default `3`) and creates `.env.example` as the canonical reference for all env vars required to run the app.

#### Scenario: SQL_RETRY_LIMIT is set
- **WHEN** `SQL_RETRY_LIMIT=5` is present in the environment
- **THEN** `SqlAgent` SHALL configure the `create_agent` recursion limit to `5 * 4 + 8 = 28`

#### Scenario: SQL_RETRY_LIMIT is absent
- **WHEN** `SQL_RETRY_LIMIT` is not set
- **THEN** `SqlAgent` SHALL use the default of `3` retries (`recursion_limit = 3 * 4 + 8 = 20`)

---

### Requirement: sql-agent-subagent-pattern

`SqlAgent` SHALL be a `create_agent()` instance with its compiled agent accessible via
`self._agent`. It SHALL be registered as a subgraph node in the outer `StateGraph`. There
SHALL be no `query_database` tool and no `get_tools()` method.

#### Scenario: supervisor routes to SQL Agent
- **WHEN** the outer graph receives a user question
- **THEN** it SHALL route directly to the SQL Agent subgraph node; the SQL Agent's internal tools MUST be invisible to the outer graph

#### Scenario: no query_database tool in supervisor graph
- **WHEN** the outer graph is built
- **THEN** the SQL Agent MUST appear as a subgraph node named `sql_agent`; no flat `query_database` tool SHALL exist

---

### Requirement: sql-tools-class

`SqlTools` SHALL be a class in `app/tools/sql_tools.py` with deps injected via
constructor. All four tools MUST be defined as `@tool` closures in `__init__` and stored
as instance attributes. `SqlAgent` SHALL instantiate `SqlTools` and pass the tools
directly to `create_agent`.

#### Scenario: tools capture injected deps
- **WHEN** `SqlTools(llm, api_base_url)` is instantiated
- **THEN** `generate_sql` SHALL capture `llm`; `execute_sql` and `handle_unidentifiable` SHALL capture `api_base_url`; all four tools MUST be available as instance attributes

#### Scenario: tools passed directly to create_agent
- **WHEN** `SqlAgent.__init__` builds the agent
- **THEN** tools SHALL be passed as `tools=[sql_tools.generate_sql, sql_tools.validate_sql, sql_tools.execute_sql, sql_tools.handle_unidentifiable]`

---

### Requirement: handle-unidentifiable

`handle_unidentifiable` SHALL be called by the SQL Agent's LLM when `generate_sql`
returns `is_identifiable=False`. It MUST write `error_message=_ERR_UNIDENTIFIED`,
`query_result=None`, and `generated_sql=None` to `WorkflowState` via `Command`.

#### Scenario: unidentifiable question triggers handle_unidentifiable
- **WHEN** `generate_sql` returns `is_identifiable=False`
- **THEN** the LLM SHALL call `handle_unidentifiable`; `validate_sql` and `execute_sql` MUST NOT be called; `error_message` SHALL be set to `Unable to identify requested entities.`

---

### Requirement: execute-sql-terminal

`execute_sql` SHALL be the sole tool that writes execution results to `WorkflowState`.
It MUST apply defense-in-depth read-only validation before calling `POST /api/query`.

#### Scenario: defense-in-depth validation fails inside execute_sql
- **WHEN** `execute_sql` receives non-SELECT SQL that bypassed `validate_sql`
- **THEN** `error_message=_ERR_VALIDATION` SHALL be written to `WorkflowState` and `POST /api/query` MUST NOT be called

#### Scenario: successful execution writes all result fields
- **WHEN** `execute_sql` receives a valid SELECT that returns rows
- **THEN** `generated_sql`, `sql_explanation`, `query_result` SHALL be set and `error_message=None` in a single `Command`

