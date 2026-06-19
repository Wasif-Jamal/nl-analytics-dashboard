## Why

Business users need to query the SQLite database using plain-English questions. Nothing can be built — no API, no UI, no analysis tools — until there is a working SQL pipeline. This change delivers that foundation: the `query_database` tool, the `WorkflowState` it operates over, the `AnalyticsGraph` it runs inside, and the read-only validation guard that keeps the database safe.

Issues #2 (API layer), #3 (Streamlit UI), and #5–#7 (visualization, insights, follow-up tools) all depend on this change being in place first. It is the build ladder's first rung.

## What Changes

- **`app/orchestration/state.py`** — new `WorkflowState` (`MessagesState` subclass) adding `question`, `generated_sql`, `sql_explanation`, `query_result` (stored as `pd.DataFrame`), `chart_config`, `insights`, `followup_questions`, `error_message` fields.
- **`app/agents/sql_agent.py`** — new `SqlAgent` class; exposes `query_database` via `get_tools()`; LLM and repository injected via constructor; owns a bounded self-correction retry loop (`SQL_RETRY_LIMIT` env var).
- **`app/orchestration/graph.py`** — new `AnalyticsGraph` class; `build()` returns `create_agent(model, tools=[query_database], system_prompt=ORCHESTRATOR_PROMPT, state_schema=WorkflowState)`; no hand-written nodes or edges.
- **`app/utils/validators.py`** — new `validate_select_only(sql: str) -> bool`; allows `SELECT` only; blocks `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`.
- **`app/services/sql_service.py`** — new `QueryService` class; intermediary between `query_database` and `QueryRepository`; enforces the call chain `query_database → QueryService → QueryRepository`.
- **`app/repositories/query_repository.py`** — new `QueryRepository` class; `execute_select(sql) -> QueryResult` (Pydantic wrapper: `dataframe`, `columns`, `row_count`); manages SQLAlchemy sessions; no business logic.
- **`app/prompts/sql_prompt.py`** — new `SQL_SYSTEM_PROMPT` constant; schema-aware system prompt for the SQL generation LLM call.
- **`app/prompts/orchestrator_prompt.py`** — new `ORCHESTRATOR_PROMPT` constant; supervisor system prompt passed to `create_agent`.
- **`app/config/env_config.py`** — new `SQL_RETRY_LIMIT` env var (default: `3`).
- **`app/schemas/sql_result.py`** — `SQLGenerationOutput` already exists (`sql`, `explanation`, `is_identifiable`). No change required.
- **Tests** — unit tests in `tests/agents/` and `tests/repositories/`; integration tests in `tests/workflows/` using an in-memory SQLite database.

## Capabilities

### New Capabilities

- `sql-pipeline`: End-to-end NL→SQL→execute pipeline. Accepts a plain-English question, generates a `SELECT` query via LLM with structured output, validates read-only compliance, executes against SQLite through `QueryRepository`, and writes results into `WorkflowState`. Includes a configurable self-correction retry loop and standard error messages for all failure paths.

### Modified Capabilities

<!-- None — this is greenfield; no existing specs to delta. -->

## Impact

- New files in `app/agents/`, `app/orchestration/`, `app/repositories/`, `app/utils/`, `app/prompts/`, `app/config/`, `tests/agents/`, `tests/repositories/`, `tests/workflows/`.
- No existing source files modified (all additions within the planned package structure from SDS §5).
- `app/schemas/sql_result.py` (`SQLGenerationOutput`) already implemented — consumed, not changed.
- `.env.example` is created in this issue as the canonical reference for all environment variables required to run the app. Initially documents `SQL_RETRY_LIMIT` and any LLM/database config vars surfaced by `env_config.py`.
