## Why

Business users need to query the Superstore database in plain English. The data layer (SQLAlchemy
models, QueryRepository, DatabaseInitializer, env/db/log config, `starter.py`) shipped in PR #11,
but there is no intelligence yet — no LLM, no prompt, no agent, no orchestration. This change
wires in FR-1 and FR-2: accept a natural-language question and translate it into a SQL query with
a plain-English explanation. It is the first node of the LangGraph pipeline and unblocks issue #2
(SQL validation) and issue #3 (query execution).

## What Changes

- **`app/config/env_config.py`** — two new settings: `llm_model` (default `gemini-2.0-flash`) and
  `llm_temperature` (default `0.0`).
- **`app/config/llm_config.py`** — `LlmConfig` class + module-level `get_llm()` factory that
  returns a configured `ChatGoogleGenerativeAI` instance.
- **`app/prompts/sql_prompt.py`** — `SQL_SYSTEM_PROMPT` constant: role, full static 4-table schema
  description, SELECT-only rule, unknown-entity instruction, and Superstore few-shot examples.
- **`app/schemas/sql_result.py`** — `SQLGenerationOutput(sql, explanation, is_identifiable)` Pydantic
  model — the structured output contract between `SqlAgent` and `SqlGenerationNode`.
- **`app/schemas/workflow_state.py`** — `WorkflowState` TypedDict (minimal: `question`,
  `generated_sql`, `sql_explanation`, `error_message`) + `initial_state(question)` factory.
- **`app/orchestration/state.py`** — thin re-export shim for `WorkflowState` / `initial_state`.
- **`app/agents/sql_agent.py`** — `SqlAgent` class: calls `llm.with_structured_output(SQLGenerationOutput)`
  with `SQL_SYSTEM_PROMPT` + user question; returns a typed `SQLGenerationOutput`.
- **`app/orchestration/nodes/sql_generation_node.py`** — `SqlGenerationNode` callable: reads
  `state["question"]`, delegates to `SqlAgent`, writes `generated_sql` / `sql_explanation` into
  state, or sets `error_message = "Unable to identify requested entities."` on failure.

## Capabilities

### New Capabilities
- `nl-sql-generation`: Accept a natural-language question and produce a structured SQL generation
  output (query + explanation + identifiability flag) via a Gemini LLM and a LangGraph-compatible
  `SqlGenerationNode`.

### Modified Capabilities

## Impact

- `env_config.py` gains two fields with safe defaults — backwards-compatible.
- Requires `GOOGLE_API_KEY` in `.env` for live LLM calls; tests mock the LLM.
- `WorkflowState` is defined minimally here; issues #2–#8 extend it with their own fields.
- No routes, Chat Service, or UI changes — those are issue #10.
- No graph assembly, validation, or execution — those are issues #2 and #3.
