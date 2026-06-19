## ADDED Requirements

### Requirement: natural-language-to-sql
A plain-English question submitted to the system SHALL be converted into a valid `SELECT` query targeting the known schema (customers, products, orders, order_items) using an LLM with structured output (`SQLGenerationOutput`).

#### Scenario: question maps to known entities
- **WHEN** a user submits a question referencing entities present in the schema (e.g. "Show monthly sales by category")
- **THEN** the system generates a valid `SELECT` query and writes it to `generated_sql` in `WorkflowState`, along with a plain-English explanation in `sql_explanation`

#### Scenario: question references unknown entities
- **WHEN** a user submits a question referencing entities not in the schema (e.g. "Show dragon sales by galaxy")
- **THEN** the tool shall not execute any query and `error_message` is set to `Unable to identify requested entities.`

#### Scenario: generated SQL is recorded
- **WHEN** `query_database` successfully generates SQL
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
`QueryRepository` SHALL only be invoked through `QueryService` and the `query_database` tool workflow. The enforced call chain is:

```
query_database → QueryService → QueryRepository → SQLite
```

No agent, route, or other service may invoke `QueryRepository` directly.

#### Scenario: query_database executes a query
- **WHEN** `query_database` calls `QueryService`, which delegates to `QueryRepository.execute_select(sql)`
- **THEN** the repository manages the SQLAlchemy session, executes the query, and returns a `QueryResult` Pydantic wrapper; no component outside this chain touches the database

---

### Requirement: tool-message-summary
The `query_database` tool SHALL return a `Command(update={...})` with a brief, fixed-template `ToolMessage` summary. The summary MUST NOT contain the full result set.

#### Scenario: successful execution
- **WHEN** `query_database` succeeds
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
- **THEN** `SqlAgent` retries up to 5 times before surfacing an error

#### Scenario: SQL_RETRY_LIMIT is absent
- **WHEN** `SQL_RETRY_LIMIT` is not set
- **THEN** `SqlAgent` uses the default of `3` retries
