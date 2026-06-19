## 1. Phase 1 — Foundation (schemas, config, dependency)

- [x] 1.1 `uv add sqlglot` — add the SQL parser dependency (updates `pyproject.toml` + `uv.lock`)
- [x] 1.2 `app/schemas/sql_result.py` — add `QueryResult(BaseModel)` (`dataframe: pd.DataFrame`, `columns: list[str]`, `row_count: int`; `model_config = ConfigDict(arbitrary_types_allowed=True)`). Keep existing `SQLGenerationOutput`.
- [x] 1.3 `app/config/env_config.py` — add `sql_retry_limit: int = 3` to `Settings`
- [x] 1.4 `app/orchestration/state.py` — `WorkflowState(MessagesState)` with `question`, `generated_sql`, `sql_explanation`, `query_result`, `chart_config`, `insights`, `followup_questions`, `error_message` (analysis fields as placeholders)
- [x] 1.5 `.env.example` — document `GOOGLE_API_KEY`, `LLM_MODEL`, `LLM_TEMPERATURE`, `DATABASE_URL`, `CSV_PATH`, `SQL_RETRY_LIMIT`

**Checkpoint:**
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## 2. Phase 2 — Core implementation

Tasks 2.1–2.3 are independent of each other — **[PARALLEL]**. Task 2.4 depends on all three; 2.5 depends on 2.4.

- [x] 2.1 **[PARALLEL]** `app/utils/validators.py` — `validate_select_only(sql: str) -> bool` using `sqlglot.parse(sql, dialect="sqlite")`; return `False` on parse error or if any top-level statement is not `sqlglot.exp.Select`
- [x] 2.2 **[PARALLEL]** `app/repositories/query_repository.py` — update `execute_select(sql) -> QueryResult` (build `QueryResult` from the DataFrame: `columns`, `row_count`); keep it free of business logic, let SQLAlchemy errors propagate
- [x] 2.3 **[PARALLEL]** `app/prompts/orchestrator_prompt.py` — `ORCHESTRATOR_PROMPT` constant (minimal: call `query_database` first, then end)
- [x] 2.4 `app/services/sql_service.py` — `QueryService(repository: QueryRepository)` with `run_query(sql) -> QueryResult` delegating to the repository *(depends on 2.2, 1.2)*
- [x] 2.5 `app/agents/sql_agent.py` — `SqlAgent` + `SqlAgentState(AgentState)` *(depends on 1.4, 2.1, 2.4)*
  - [x] 2.5.1 `SqlAgentState(AgentState)` — adds `query_result: Optional[QueryResult]`, `error_type: Optional[str]` (`from langchain.agents import AgentState` — verified)
  - [x] 2.5.2 inner `validate_and_execute` `@tool` (closure over `query_service`) — returns `Command` updating `SqlAgentState`; `error_type="validation"` on guard failure, `error_type="database"` on execution exception, `query_result` + summary `ToolMessage` on success
  - [x] 2.5.3 build inner agent via `create_agent(model=llm, tools=[validate_and_execute], system_prompt=SQL_SYSTEM_PROMPT, response_format=SQLGenerationOutput, state_schema=SqlAgentState)`
  - [x] 2.5.4 `query_database` `@tool` (returned by `get_tools()`) — invokes inner agent with `config={"recursion_limit": retry_limit * 2 + 1}`; maps `is_identifiable=False` / validation / database / empty / success to the correct `Command` updates (clears `error_message` on success, `query_result=None` on every failure; `ToolMessage` uses fixed template)

**Checkpoint:**
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## 3. Phase 3 — Integration (graph wiring)

- [x] 3.1 `app/orchestration/graph.py` — `AnalyticsGraph(llm, query_service, retry_limit)`; `build()` returns `create_agent(model=llm, tools=SqlAgent(...).get_tools(), system_prompt=ORCHESTRATOR_PROMPT, state_schema=WorkflowState)` *(depends on 1.4, 2.3, 2.5)*
- [x] 3.2 Smoke-verified `build()` compiles with `state_schema=WorkflowState` (MessagesState subclass accepted — **no AgentState fallback needed**); nodes `__start__→model→tools→__end__`, `query_database` registered in `graph.nodes["tools"].bound.tools_by_name`

**Checkpoint:**
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## 4. Phase 4 — Tests (one test per spec scenario)

- [ ] 4.1 `tests/utils/test_validators.py` *(spec: read-only-validation)*
  - [ ] 4.1.1 plain `SELECT` → `True`
  - [ ] 4.1.2 CTE (`WITH cte AS (SELECT ...) SELECT ...`) → `True`
  - [ ] 4.1.3 each blocked keyword `INSERT`/`UPDATE`/`DELETE`/`DROP`/`ALTER`/`TRUNCATE` → `False`
  - [ ] 4.1.4 lowercase variant (`insert into ...`) → `False`
  - [ ] 4.1.5 multi-statement with a non-SELECT → `False`
  - [ ] 4.1.6 malformed/unparseable SQL → `False`
- [x] 4.2 `tests/repositories/test_query_repository.py` — update existing 3 tests to assert `QueryResult` shape (`dataframe`, `columns`, `row_count`) *(spec: sql-execution)* — pulled forward with 2.2; also fixed the incidental `tests/utils/test_database_initializer.py` caller
- [ ] 4.3 `tests/services/test_sql_service.py` — mock `QueryRepository`; assert `run_query` delegates and returns `QueryResult` *(spec: database-access-boundary)*
- [ ] 4.4 `tests/agents/test_sql_agent.py` — mock `self._agent.invoke` return dicts *(spec: natural-language-to-sql, sql-self-correction-retry, sql-execution, tool-message-summary)*
  - [ ] 4.4.1 `is_identifiable=False` → `error_message="Unable to identify requested entities."`, `query_result=None`
  - [ ] 4.4.2 inner returns `query_result` → `query_result` set, `error_message=None`, ToolMessage matches `"retrieved {n} rows. Columns: ..."`
  - [ ] 4.4.3 inner `error_type="validation"` → `error_message="Generated query could not be validated."`, `query_result=None`
  - [ ] 4.4.4 inner `error_type="database"` → `error_message="Unable to retrieve data at this time."`, `query_result=None`
  - [ ] 4.4.5 `row_count==0` → `error_message="No data found for the requested query."`, `query_result=None`
  - [ ] 4.4.6 `generated_sql` + `sql_explanation` written on success and execution-failure paths
- [ ] 4.5 `tests/orchestration/test_graph.py` *(spec: workflow-state, database-access-boundary)*
  - [ ] 4.5.1 `AnalyticsGraph.build()` returns a compiled graph
  - [ ] 4.5.2 compiled graph includes `query_database` in its tool registry
- [ ] 4.6 `tests/workflows/test_sql_pipeline.py` — integration over `initialized_engine` (in-memory SQLite); mock the inner agent's `validate_and_execute` *(spec: all)*
  - [ ] 4.6.1 happy path → `query_result` populated, `generated_sql` written, ToolMessage template, `error_message=None`
  - [ ] 4.6.2 unknown entities → `error_message` set, `query_result=None`, no DB call
  - [ ] 4.6.3 execution retry → first call bad column (raises), second succeeds → result in state
  - [ ] 4.6.4 read-only guard → `DELETE` blocked → `error_message="Generated query could not be validated."`
  - [ ] 4.6.5 database error → `run_query` raises → `error_message="Unable to retrieve data at this time."`
  - [ ] 4.6.6 empty result → `error_message="No data found for the requested query."`, `query_result=None`

**Checkpoint (final gate):**
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## 5. Phase 5 — Finalize

- [ ] 5.1 `openspec validate sql-pipeline` passes
- [ ] 5.2 All quality gates green; reconcile any deviations back into `plan.md`
