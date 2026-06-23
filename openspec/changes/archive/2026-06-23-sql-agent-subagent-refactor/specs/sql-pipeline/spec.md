# sql-pipeline Spec Delta — SQL Agent Subagent Refactor

## MODIFIED Requirements

### Requirement: natural-language-to-sql

The system SHALL generate SQL via the `generate_sql` internal tool of `SqlTools`, which
makes a nested `llm.with_structured_output(SQLGenerationOutput)` call. The SQL Agent's
outer `create_agent` LLM MUST orchestrate tool-calling order; it SHALL NOT generate SQL
itself. All references to `query_database` SHALL be replaced by the tool chain:
`generate_sql → validate_sql → execute_sql` (or `handle_unidentifiable`).

#### Scenario: question maps to known entities
- **WHEN** a user submits a question referencing entities in the schema
- **THEN** `generate_sql` produces a `SQLGenerationOutput` with `is_identifiable=True`, `validate_sql` passes, and `execute_sql` writes `generated_sql` and `sql_explanation` to `WorkflowState`

#### Scenario: question references unknown entities
- **WHEN** `generate_sql` returns `is_identifiable=False`
- **THEN** `handle_unidentifiable` is called; no query is executed; `error_message` is set to `Unable to identify requested entities.`

#### Scenario: generated SQL is recorded
- **WHEN** `execute_sql` succeeds
- **THEN** `generated_sql`, `sql_explanation`, and `query_result` SHALL be written to `WorkflowState` in the same `Command`

---

### Requirement: read-only-validation

The system SHALL enforce read-only validation at two points: `validate_sql` MUST provide
the primary check and feed back to the LLM for retry; `execute_sql` SHALL apply a
defense-in-depth `validate_select_only` check before calling the API. Both MUST use
`app/utils/validators.validate_select_only`.

#### Scenario: valid SELECT query
- **WHEN** the generated SQL is a `SELECT` statement
- **THEN** `validate_sql` SHALL return `{"valid": True}` and the LLM SHALL proceed to call `execute_sql`

#### Scenario: write or DDL statement generated
- **WHEN** the generated SQL contains `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, or `TRUNCATE`
- **THEN** `validate_sql` SHALL return `{"valid": False, "reason": "..."}` and the LLM MUST retry `generate_sql`; if the defense-in-depth check inside `execute_sql` catches it, `error_message` SHALL be set to `Generated query could not be validated.`

---

### Requirement: sql-self-correction-retry

The retry loop SHALL be driven by the SQL Agent's own `create_agent` ReAct mechanism.
`SQL_RETRY_LIMIT` MUST bound the agent's recursion limit as
`recursion_limit = retry_limit * 2 + 1`. On `validate_sql` failure or `execute_sql`
failure, the LLM SHALL call `generate_sql` again with error context visible in its
message history.

#### Scenario: validation fails then succeeds within retry limit
- **WHEN** the first `validate_sql` call returns `{"valid": False}` but a subsequent attempt within the retry limit passes
- **THEN** the valid query SHALL be executed and results written to `WorkflowState`

#### Scenario: execution fails due to bad SQL then succeeds within retry limit
- **WHEN** `execute_sql` fails and a subsequent attempt within the retry limit succeeds
- **THEN** the corrected query SHALL be executed and results written to `WorkflowState`

#### Scenario: all retries exhausted
- **WHEN** every attempt within the retry limit fails validation or execution
- **THEN** `error_message` SHALL be set to `Generated query could not be validated.` and `query_result` MUST remain `None`

---

### Requirement: sql-execution

`execute_sql` SHALL call `POST /api/query` via `httpx` and write results to `WorkflowState`
via `Command`. The call chain MUST be:
`execute_sql → POST /api/query → QueryRouter → QueryService → QueryRepository → SQLite`.

#### Scenario: query returns rows
- **WHEN** `execute_sql` calls `POST /api/query` and rows are returned
- **THEN** `generated_sql`, `sql_explanation`, `query_result` SHALL be set and `error_message=None` in a single `Command`

#### Scenario: query returns zero rows
- **WHEN** `execute_sql` calls `POST /api/query` and zero rows are returned
- **THEN** `error_message` SHALL be set to `No data found for the requested query.` and `query_result` MUST be `None`

#### Scenario: database error
- **WHEN** `POST /api/query` raises an HTTP or connection error
- **THEN** `error_message` SHALL be set to `Unable to retrieve data at this time.` and `query_result` MUST be `None`

---

### Requirement: database-access-boundary

`execute_sql` SHALL be the sole tool permitted to call `POST /api/query`. No other tool,
agent, route, or service MUST invoke `QueryRepository` directly.

#### Scenario: execute_sql calls the query API
- **WHEN** `execute_sql` is called with a validated SELECT query
- **THEN** it SHALL POST to `/api/query`; `QueryRepository` MUST NOT be invoked by any other tool, agent, or component

---

### Requirement: tool-message-summary

`execute_sql` SHALL return a `Command` with a `ToolMessage` following the fixed template.
`handle_unidentifiable` and `execute_sql` (on error) SHALL each return a brief
`ToolMessage` that the SQL Agent's LLM MUST use as self-correction context.

#### Scenario: successful execution
- **WHEN** `execute_sql` succeeds
- **THEN** the `ToolMessage` content SHALL follow the template: `"retrieved {row_count} rows. Columns: {col1}, {col2}, …"` and the full result MUST live in `query_result` state only

---

### Requirement: env-configuration

`SQL_RETRY_LIMIT` SHALL bound the SQL Agent's `create_agent` recursion limit as
`recursion_limit = retry_limit * 2 + 1`.

#### Scenario: SQL_RETRY_LIMIT is set
- **WHEN** `SQL_RETRY_LIMIT=5` is present in the environment
- **THEN** `SqlAgent` SHALL configure the `create_agent` recursion limit to `5 * 2 + 1 = 11`

#### Scenario: SQL_RETRY_LIMIT is absent
- **WHEN** `SQL_RETRY_LIMIT` is not set
- **THEN** `SqlAgent` SHALL use the default of `3` retries (`recursion_limit=7`)

---

## ADDED Requirements

### Requirement: sql-agent-subagent-pattern

`SqlAgent` SHALL be a `create_agent()` instance with its compiled agent accessible via
`self._agent`. It SHALL be registered as a subagent in the supervisor via
`create_supervisor`. There SHALL be no `query_database` tool and no `get_tools()` method.

#### Scenario: supervisor routes to SQL Agent
- **WHEN** the supervisor receives a user question
- **THEN** it SHALL invoke the SQL Agent via the handoff tool generated by `create_supervisor`; the SQL Agent's internal tools MUST be invisible to the supervisor

#### Scenario: no query_database tool in supervisor graph
- **WHEN** the supervisor graph is built
- **THEN** there SHALL be no `query_database` tool in the supervisor's tool registry; the SQL Agent MUST appear as a subagent node

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

---

## REMOVED Requirements

### Requirement: query-database-tool

The `query_database` tool and `SqlAgent.get_tools()` method SHALL be removed. The SQL
Agent MUST NOT be exposed as a flat tool to the supervisor; it SHALL be a `create_agent()`
subagent registered via `create_supervisor`.

#### Scenario: query_database no longer exists
- **WHEN** the supervisor graph is compiled
- **THEN** no tool named `query_database` SHALL exist in any tool registry
