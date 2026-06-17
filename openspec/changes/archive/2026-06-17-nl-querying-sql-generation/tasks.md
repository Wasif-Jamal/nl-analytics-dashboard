# Tasks: nl-querying-sql-generation

Sequenced implementation checklist. Tests are written alongside Phase 2 (one test per spec
scenario). Quality gates run after every phase — all three must be green before moving on.

---

## Phase 1 — Foundation (shared contracts everything else imports)

- [x] 1.1 **`app/config/env_config.py`** (modify) — add `llm_model: str = "gemini-2.0-flash"` and
  `llm_temperature: float = 0.0` to `Settings`; update the class docstring with both new attrs
- [x] 1.2 **`app/schemas/sql_result.py`** (create) — `SQLGenerationOutput(sql, explanation, is_identifiable=True)` Pydantic model; module + class docstrings
- [x] 1.3 **`app/schemas/workflow_state.py`** (create) — `WorkflowState(TypedDict)` with
  `question`, `generated_sql`, `sql_explanation`, `error_message: Optional[str]`; `initial_state(question)` factory function
- [x] 1.4 **`app/schemas/__init__.py`** (update) — export `SQLGenerationOutput`, `WorkflowState`, `initial_state`

### ✅ Checkpoint 1
```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest
```

---

## Phase 2 — Core Implementation

Tasks 2.1–2.2 are **[PARALLEL]** — they have no dependency on each other.

- [x] 2.1 **[PARALLEL] `app/config/llm_config.py`** (create) — `LlmConfig` class with
  `get_llm() -> ChatGoogleGenerativeAI`; reads `settings.llm_model`, `settings.llm_temperature`,
  `settings.google_api_key`; module-level `_config = LlmConfig()` singleton + `get_llm()` wrapper;
  logs model + temperature at initialization
- [x] 2.2 **[PARALLEL] `app/prompts/sql_prompt.py`** (create) — `SQL_SYSTEM_PROMPT` string constant:
  - Role: expert SQLite analyst, read-only SELECT only
  - Full static schema: all 4 tables with column names, types, PKs, FKs, and sample enum values
  - Rules: SELECT only; no SQL comments in output; valid SQLite syntax; set `is_identifiable=false` for unknown entities
  - Three few-shot examples: "Show total sales by region", "Top 10 products by revenue", "Show dragon sales by galaxy" (negative example)
- [x] 2.3 **`app/orchestration/state.py`** (create) — thin re-export shim:
  `from app.schemas.workflow_state import WorkflowState, initial_state; __all__ = [...]`
- [x] 2.4 **`app/agents/sql_agent.py`** (create) — `SqlAgent` class:
  - `__init__(self, llm=None)` defaults to `get_llm()`
  - `generate(self, question: str) -> SQLGenerationOutput` builds `[SystemMessage(SQL_SYSTEM_PROMPT), HumanMessage(question)]`,
    calls `self._llm.with_structured_output(SQLGenerationOutput).invoke(messages)`, logs start + result
- [x] 2.5 **`app/orchestration/nodes/sql_generation_node.py`** (create) — `SqlGenerationNode` class:
  - `__init__(self, agent: SqlAgent | None = None)` defaults to `SqlAgent()`
  - `__call__(self, state: WorkflowState) -> WorkflowState`:
    success + `is_identifiable=True` → `{**state, "generated_sql": ..., "sql_explanation": ...}`;
    `is_identifiable=False` → `{**state, "error_message": "Unable to identify requested entities."}`;
    exception → same error message + `logger.exception`

Tasks 2.6–2.9 are **[PARALLEL]** — independent `__init__.py` updates.

- [x] 2.6 **[PARALLEL] `app/agents/__init__.py`** (update) — export `SqlAgent`
- [x] 2.7 **[PARALLEL] `app/prompts/__init__.py`** (update) — export `SQL_SYSTEM_PROMPT`
- [x] 2.8 **[PARALLEL] `app/orchestration/__init__.py`** (update) — export `WorkflowState`, `initial_state`
- [x] 2.9 **[PARALLEL] `app/orchestration/nodes/__init__.py`** (update) — export `SqlGenerationNode`

### ✅ Checkpoint 2
```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest
```

---

## Phase 3 — Integration Smoke

- [x] 3.1 Verify top-level imports resolve without error
- [x] 3.2 Verify `SqlGenerationNode` can be instantiated with a mocked agent (no LLM call made)

### ✅ Checkpoint 3
```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest
```

---

## Phase 4 — Tests (one test per spec scenario)

- [x] 4.1 **`tests/config/test_llm_config.py`** (create):
  - `test_get_llm_returns_chat_google_generative_ai`
  - `test_get_llm_uses_settings_model`

- [x] 4.2 **`tests/orchestration/__init__.py`** (create) — empty package marker

- [x] 4.3 **`tests/agents/test_sql_agent.py`** (create):
  - `test_generate_returns_sql_generation_output`
    → **spec scenario:** *"Identifiable question"*
  - `test_generate_unidentifiable_question`
    → **spec scenario:** *"Unidentifiable question"*

- [x] 4.4 **`tests/orchestration/test_sql_generation_node.py`** (create):
  - `test_node_success_sets_sql_and_explanation`
    → **spec scenario:** *"Valid business question"*
  - `test_node_unidentifiable_sets_error_message`
    → **spec scenario:** *"Unknown schema entities"*
  - `test_node_exception_sets_error_message`
    → **spec scenario:** *"LLM call fails"*

### ✅ Final Checkpoint
```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest
```

27/27 tests passed.

---

## Spec Scenario → Test Mapping

| Spec Scenario | Test |
|---|---|
| Identifiable question | `tests/agents/test_sql_agent.py::test_generate_returns_sql_generation_output` |
| Unidentifiable question | `tests/agents/test_sql_agent.py::test_generate_unidentifiable_question` |
| Valid business question | `tests/orchestration/test_sql_generation_node.py::test_node_success_sets_sql_and_explanation` |
| Unknown schema entities | `tests/orchestration/test_sql_generation_node.py::test_node_unidentifiable_sets_error_message` |
| LLM call fails | `tests/orchestration/test_sql_generation_node.py::test_node_exception_sets_error_message` |
