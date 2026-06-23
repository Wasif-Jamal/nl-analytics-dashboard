# Implementation Plan: SQL Agent Subagent Refactor

## Summary

Nine files change: 2 created, 3 rewritten, 4 updated.
No schema changes — `WorkflowState`, `SQLGenerationOutput`, `QueryResult` are all unchanged.

---

## Architecture Decisions

| Decision | Choice | Reason |
|---|---|---|
| Tools location | `app/tools/sql_tools.py` (`SqlTools` class) | OOP convention; deps injected via constructor; closures as instance attrs |
| `generate_sql` LLM call | Nested `llm.with_structured_output(SQLGenerationOutput)` | Option A — clean typed output; outer agent orchestrates, inner call generates |
| `is_identifiable=False` path | Separate `handle_unidentifiable` tool | Option B — keeps `execute_sql` focused on execution outcomes only |
| State schema | `WorkflowState` shared by SQL agent and supervisor | Tools write directly to `WorkflowState` via `Command`; no `SqlAgentState` |
| Recursion limit | `self._agent = create_agent(...).with_config({"recursion_limit": retry * 2 + 1})` | Binds limit at agent level so `create_supervisor` inherits it without extra wiring |
| Supervisor | `create_supervisor(agents=[sql_agent._agent], model=llm, prompt=ORCHESTRATOR_PROMPT, state_schema=WorkflowState).compile()` | `create_supervisor` auto-generates `transfer_to_sql_agent` handoff tool |

---

## Files

### CREATE

**`app/tools/__init__.py`** — empty package init.

**`app/tools/sql_tools.py`**

```python
"""SQL tools provided to SqlAgent via SqlTools."""

from typing import Annotated
import httpx
import pandas as pd
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Command

from app.config.log_config import config as log_config
from app.prompts.sql_prompt import SQL_SYSTEM_PROMPT
from app.schemas.sql_result import QueryResult, SQLGenerationOutput
from app.utils.validators import validate_select_only

logger = log_config.get_logger(__name__)

_ERR_UNIDENTIFIED = "Unable to identify requested entities."
_ERR_VALIDATION   = "Generated query could not be validated."
_ERR_DATABASE     = "Unable to retrieve data at this time."
_ERR_EMPTY        = "No data found for the requested query."


class SqlTools:
    """Builds the four internal tools for SqlAgent.

    All tools are @tool-decorated closures defined in __init__ that capture
    injected dependencies (llm, api_base_url) and are exposed as instance
    attributes. SqlAgent passes them directly to create_agent.

    Args:
        llm: Chat model for the generate_sql nested structured-output call.
        api_base_url: Base URL for POST /api/query calls in execute_sql.
    """

    def __init__(self, llm, api_base_url: str) -> None:

        @tool
        def generate_sql(question: str) -> SQLGenerationOutput:
            """Generate a SQLite SELECT query for the question.

            Makes a nested llm.with_structured_output(SQLGenerationOutput) call.
            Returns SQLGenerationOutput with is_identifiable=False if the question
            references entities not in the schema.

            Args:
                question: The user's natural-language question.
            """
            chain = llm.with_structured_output(SQLGenerationOutput)
            result: SQLGenerationOutput = chain.invoke([
                SystemMessage(content=SQL_SYSTEM_PROMPT),
                HumanMessage(content=question),
            ])
            logger.debug(
                "generate_sql: identifiable=%s sql=%.200s",
                result.is_identifiable,
                result.sql or "",
            )
            return result

        @tool
        def validate_sql(sql: str) -> dict:
            """Validate that sql is a SELECT-only statement.

            Returns {"valid": True} on success or {"valid": False, "reason": "..."}.
            Feedback only — the caller LLM retries generate_sql on failure.

            Args:
                sql: The generated SQL to validate.
            """
            if validate_select_only(sql):
                logger.debug("validate_sql: passed")
                return {"valid": True}
            logger.warning("validate_sql: rejected non-SELECT sql=%.200s", sql)
            return {
                "valid": False,
                "reason": "Only SELECT statements are permitted. Rewrite the query.",
            }

        @tool
        def execute_sql(
            sql: str,
            explanation: str,
            tool_call_id: Annotated[str, InjectedToolCallId],
        ) -> Command:
            """Defense-in-depth validate then POST /api/query. Writes results to WorkflowState.

            Applies a secondary validate_select_only check before calling the API.
            On success writes generated_sql, sql_explanation, query_result, and
            error_message=None. On failure writes error_message and clears query_result.

            Args:
                sql: The validated SELECT query to execute.
                explanation: Plain-English explanation of the query from generate_sql.
                tool_call_id: Injected ToolMessage id.
            """
            if not validate_select_only(sql):
                logger.warning("execute_sql: defense-in-depth check failed sql=%.200s", sql)
                return Command(update={
                    "error_message": _ERR_VALIDATION,
                    "query_result": None,
                    "messages": [ToolMessage(
                        content=_ERR_VALIDATION, tool_call_id=tool_call_id
                    )],
                })
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
            except Exception as exc:  # noqa: BLE001
                logger.warning("execute_sql: HTTP/DB error: %s", exc)
                return Command(update={
                    "error_message": _ERR_DATABASE,
                    "query_result": None,
                    "messages": [ToolMessage(
                        content=f"Execution error: {exc!s}. Correct the query and retry.",
                        tool_call_id=tool_call_id,
                    )],
                })
            if result.row_count == 0:
                logger.warning("execute_sql: query returned 0 rows")
                return Command(update={
                    "error_message": _ERR_EMPTY,
                    "query_result": None,
                    "generated_sql": sql,
                    "sql_explanation": explanation,
                    "messages": [ToolMessage(content=_ERR_EMPTY, tool_call_id=tool_call_id)],
                })
            summary = (
                f"retrieved {result.row_count} rows. "
                f"Columns: {', '.join(result.columns)}"
            )
            logger.info("execute_sql: %s", summary)
            return Command(update={
                "generated_sql": sql,
                "sql_explanation": explanation,
                "query_result": result,
                "error_message": None,
                "messages": [ToolMessage(content=summary, tool_call_id=tool_call_id)],
            })

        @tool
        def handle_unidentifiable(
            tool_call_id: Annotated[str, InjectedToolCallId],
        ) -> Command:
            """Terminal handler when generate_sql returns is_identifiable=False.

            Writes error_message=_ERR_UNIDENTIFIED, clears query_result and
            generated_sql in WorkflowState. validate_sql and execute_sql MUST
            NOT be called after this tool.

            Args:
                tool_call_id: Injected ToolMessage id.
            """
            logger.warning("handle_unidentifiable: entities not in schema")
            return Command(update={
                "error_message": _ERR_UNIDENTIFIED,
                "query_result": None,
                "generated_sql": None,
                "messages": [ToolMessage(
                    content=_ERR_UNIDENTIFIED, tool_call_id=tool_call_id
                )],
            })

        self.generate_sql = generate_sql
        self.validate_sql = validate_sql
        self.execute_sql = execute_sql
        self.handle_unidentifiable = handle_unidentifiable
```

---

### REWRITE

**`app/agents/sql_agent.py`** — remove `SqlAgentState`, `_build_validate_and_execute()`, `get_tools()`.

Key shape:
```python
from langchain.agents import create_agent
from app.tools.sql_tools import SqlTools
from app.orchestration.state import WorkflowState

class SqlAgent:
    def __init__(self, llm, api_base_url=None, retry_limit=None):
        self._retry_limit = retry_limit if retry_limit is not None else settings.sql_retry_limit
        sql_tools = SqlTools(llm=llm, api_base_url=api_base_url or settings.api_base_url)
        self._agent = create_agent(
            model=llm,
            tools=[
                sql_tools.generate_sql,
                sql_tools.validate_sql,
                sql_tools.execute_sql,
                sql_tools.handle_unidentifiable,
            ],
            system_prompt=SQL_SYSTEM_PROMPT,
            state_schema=WorkflowState,
            name="sql_agent",
        ).with_config({"recursion_limit": self._retry_limit * 2 + 1})
```

Docstrings, logging, and error constants migrate as-is from the existing file.
No `get_tools()` method. `self._agent` is the only public surface.

---

**`app/prompts/sql_prompt.py`** — update workflow instructions.

Replace the three-step `validate_and_execute` workflow with the four-tool workflow:

```
STEP 1 — Call generate_sql with the user's question to obtain sql, explanation,
          and is_identifiable.
STEP 2 — If is_identifiable is false, call handle_unidentifiable and stop.
STEP 3 — Call validate_sql with the generated sql.
          If valid is false, fix the query: call generate_sql again with the
          error context, then retry from STEP 3.
STEP 4 — Call execute_sql with sql and explanation. This stores the result.
          If it fails, correct and retry from STEP 1 with the error context.
```

Keep the DATABASE SCHEMA and SQL RULES sections unchanged — they are the content
`generate_sql` passes as the system message in its nested LLM call.

---

**`app/prompts/orchestrator_prompt.py`** — replace `query_database` with handoff tool.

`create_supervisor` auto-generates `transfer_to_sql_agent` from the agent's `name="sql_agent"`.

New prompt shape:
```
You are an analytics supervisor. A business user asks a question about the data,
and you coordinate agents to answer it.

You have one agent available:
- transfer_to_sql_agent: routes the question to the SQL Agent, which generates,
  validates, and executes the corresponding SQL query.

Instructions:
1. For any data question, call transfer_to_sql_agent exactly once.
2. After the SQL Agent returns, do not call it again. Provide a brief closing
   message — the application reads the structured result from state.
3. Never attempt to write or fabricate SQL, data, or analysis yourself.
```

---

**`app/orchestration/graph.py`** — replace supervisor construction.

```python
from langgraph_supervisor import create_supervisor
from app.agents.sql_agent import SqlAgent
from app.orchestration.state import WorkflowState
from app.prompts.orchestrator_prompt import ORCHESTRATOR_PROMPT

class AnalyticsGraph:
    def build(self) -> CompiledStateGraph:
        sql_agent = SqlAgent(self._llm, retry_limit=self._retry_limit)
        logger.info("Building analytics supervisor with sql_agent subagent")
        graph = create_supervisor(
            agents=[sql_agent._agent],
            model=self._llm,
            prompt=ORCHESTRATOR_PROMPT,
            state_schema=WorkflowState,
        ).compile()
        logger.info("Supervisor graph compiled successfully")
        return graph
```

Return type (`CompiledStateGraph`) is unchanged.

---

### UPDATE

**`tests/agents/test_sql_agent.py`** — rewrite to test four tools directly.

Helpers:
```python
def _make_sql_tools(llm=None, api_base_url="http://testserver"):
    from app.tools.sql_tools import SqlTools
    llm = llm or ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key="test-key")
    return SqlTools(llm=llm, api_base_url=api_base_url)
```

Test coverage (one test per scenario, matching spec):

| Test | Tool | Mock | Asserts |
|---|---|---|---|
| `test_generate_sql_identifiable` | `generate_sql` | `llm.with_structured_output` return | `is_identifiable=True`, correct sql |
| `test_generate_sql_unidentifiable` | `generate_sql` | same | `is_identifiable=False` |
| `test_validate_sql_valid_select` | `validate_sql` | none | `{"valid": True}` |
| `test_validate_sql_rejects_write` | `validate_sql` | none | `valid=False, "reason" in result` |
| `test_execute_sql_success` | `execute_sql` | `httpx.Client` | `query_result.row_count==1`, `error_message=None`, template summary |
| `test_execute_sql_zero_rows` | `execute_sql` | `httpx.Client` (0 rows) | `error_message=_ERR_EMPTY`, `query_result=None` |
| `test_execute_sql_defense_in_depth_blocks_write` | `execute_sql` | none | `error_message=_ERR_VALIDATION`, no HTTP call |
| `test_execute_sql_http_error` | `execute_sql` | `httpx.Client` raises | `error_message=_ERR_DATABASE` |
| `test_handle_unidentifiable` | `handle_unidentifiable` | none | `error_message=_ERR_UNIDENTIFIED`, `query_result=None`, `generated_sql=None` |
| `test_retry_limit_sourced_from_settings` | `SqlAgent` | monkeypatch settings | `_retry_limit == 5` |
| `test_retry_limit_defaults_to_settings_value` | `SqlAgent` | none | `_retry_limit == 3` |

**`tests/workflows/test_sql_pipeline.py`** — update to drive via `SqlTools.execute_sql`.

Keep `_QueryServiceTransport`, `_make_test_client`. Remove `_ScriptedInnerAgent` and the `get_tools()[0]` usage. Tests now call `execute_sql.func()` directly with real SQL against the initialized DB via the transport.

Helper:
```python
def _make_tools(initialized_engine):
    service = QueryService(repository=QueryRepository(db_engine=initialized_engine))
    http_client = _make_test_client(service)
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key="test-key")
    tools = SqlTools(llm=llm, api_base_url="http://testserver")
    return tools, http_client

def _run_execute(tools, http_client, sql, explanation="explanation", tool_call_id="call_1"):
    with patch("app.tools.sql_tools.httpx.Client") as mock_cls:
        mock_cls.return_value.__enter__.return_value = http_client
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        return tools.execute_sql.func(sql=sql, explanation=explanation, tool_call_id=tool_call_id).update
```

Preserve all 8 existing test scenarios (happy path, unknown entities, execution retry, validation failure, all attempts fail, read-only guard, database error, empty result). The "unknown entities" and "retry" scenarios now test `validate_sql` + `execute_sql` in sequence rather than via the outer agent wrapper.

**`tests/orchestration/test_graph.py`** — update node assertions.

Replace:
```python
def test_query_database_is_registered():
    graph = _build()
    tool_names = set(graph.nodes["tools"].bound.tools_by_name)
    assert "query_database" in tool_names
```

With:
```python
def test_sql_agent_is_registered_as_subagent():
    """create_supervisor registers sql_agent as a subagraph node."""
    graph = _build()
    assert "sql_agent" in graph.nodes

def test_no_query_database_in_supervisor():
    """query_database tool must not appear anywhere in the compiled supervisor."""
    graph = _build()
    tool_names = set(graph.nodes["tools"].bound.tools_by_name)
    assert "query_database" not in tool_names
```

Keep `test_build_returns_compiled_graph` with updated node check (supervisor graph nodes differ from the flat `create_agent` graph).

---

## Task Order (dependency-safe)

Tasks 1, 3, 4, and 6 have no inter-task dependencies and can proceed in parallel.
Tasks 2 and 7 depend on Task 1.
Task 5 depends on Tasks 2 and 4.
Task 8 depends on Task 5.
Quality gates are last.

```
1. Create app/tools/__init__.py + app/tools/sql_tools.py
2. Rewrite app/agents/sql_agent.py               [after 1]
3. Update app/prompts/sql_prompt.py
4. Update app/prompts/orchestrator_prompt.py
5. Rewrite app/orchestration/graph.py            [after 2, 4]
6. Rewrite tests/agents/test_sql_agent.py        [after 1]
7. Update tests/workflows/test_sql_pipeline.py   [after 1]
8. Update tests/orchestration/test_graph.py      [after 5]
9. Quality gates: ruff check → ruff format --check → pytest
```

---

## Quality Gates

Run in order; all must be green before committing:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## Unchanged

`app/orchestration/state.py` · `app/schemas/` · `app/utils/validators.py`
`app/repositories/` · `app/services/` · `app/models/` · `app/routes/` · `website/app.py`
`tests/conftest.py` (fixtures `initialized_engine`, `sample_csv`, `temp_engine`)
