"""Integration tests for the SQL pipeline against a real SQLite database.

These exercise the real validation → /api/query → QueryService → QueryRepository
→ SQLite path using the ``initialized_engine`` fixture. The HTTP call from
``validate_and_execute`` is intercepted by a custom sync ``httpx.BaseTransport``
that routes the request directly to ``QueryService`` (no network required).
Only the LLM's decisions are scripted via a fake inner agent; everything
downstream is real.

Covers spec scenarios across natural-language-to-sql, read-only-validation,
sql-self-correction-retry, sql-execution, and tool-message-summary.
"""

import json
from unittest.mock import MagicMock, patch

import httpx
from langchain_google_genai import ChatGoogleGenerativeAI
from sqlalchemy import Engine

from app.agents.sql_agent import SqlAgent
from app.repositories.query_repository import QueryRepository
from app.schemas.sql_result import SQLGenerationOutput
from app.services.sql_service import QueryService
from app.utils.validators import validate_select_only

_REVENUE_SQL = (
    "SELECT o.region, ROUND(SUM(oi.sales), 2) AS revenue "
    "FROM order_items oi JOIN orders o ON oi.order_id = o.order_id "
    "GROUP BY o.region"
)


class _QueryServiceTransport(httpx.BaseTransport):
    """Sync httpx transport that routes POST /api/query directly to QueryService.

    Mirrors the route-level validation and serialization of ``QueryRouter``
    without requiring a running server or ASGI transport.
    """

    def __init__(self, service: QueryService) -> None:
        self._service = service

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        data = json.loads(request.content)
        sql = data["sql"]
        if not validate_select_only(sql):
            return httpx.Response(
                400,
                headers={"content-type": "application/json"},
                content=json.dumps(
                    {"detail": "Generated query could not be validated."}
                ).encode(),
            )
        try:
            result = self._service.run_query(sql)
            body = {
                "columns": result.columns,
                "rows": result.dataframe.to_dict(orient="records"),
                "row_count": result.row_count,
            }
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                content=json.dumps(body).encode(),
            )
        except Exception:
            return httpx.Response(
                500,
                headers={"content-type": "application/json"},
                content=json.dumps({"detail": "DB error"}).encode(),
            )


def _make_test_client(service: QueryService) -> httpx.Client:
    return httpx.Client(
        transport=_QueryServiceTransport(service), base_url="http://testserver"
    )


class _ScriptedInnerAgent:
    """Fake inner create_agent: runs the real inner tool for each scripted SQL.

    Each scripted SQL is actually validated and executed via the test HTTP
    client, then the final state dict is returned with the supplied structured
    response.
    """

    def __init__(self, inner_tool, sqls, structured, http_client: httpx.Client):
        self._inner_tool = inner_tool
        self._sqls = sqls
        self._structured = structured
        self._http_client = http_client

    def invoke(self, _input, config=None):
        state = {"structured_response": self._structured}
        for sql in self._sqls:
            with patch("app.agents.sql_agent.httpx.Client") as mock_cls:
                mock_cls.return_value.__enter__.return_value = self._http_client
                mock_cls.return_value.__exit__ = MagicMock(return_value=False)
                command = self._inner_tool.func(sql=sql, tool_call_id="inner")
            state.update(command.update)
        return state


def _pipeline(initialized_engine: Engine, sqls, structured):
    """Build the query_database tool wired to the real DB via a test HTTP client."""
    service = QueryService(repository=QueryRepository(db_engine=initialized_engine))
    http_client = _make_test_client(service)

    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key="test-key")
    agent = SqlAgent(llm, api_base_url="http://testserver", retry_limit=3)
    agent._agent = _ScriptedInnerAgent(
        agent._build_validate_and_execute(), sqls, structured, http_client=http_client
    )
    return agent.get_tools()[0]


def _identifiable(sql: str) -> SQLGenerationOutput:
    return SQLGenerationOutput(sql=sql, explanation="explanation", is_identifiable=True)


def _run(tool, question: str = "show total sales by region") -> dict:
    return tool.func(question=question, tool_call_id="call_1", _state={}).update


def test_happy_path_populates_result(initialized_engine: Engine):
    """A valid question runs real SQL and stores the QueryResult in state."""
    tool = _pipeline(initialized_engine, [_REVENUE_SQL], _identifiable(_REVENUE_SQL))
    update = _run(tool)
    assert update["error_message"] is None
    assert update["generated_sql"] == _REVENUE_SQL
    result = update["query_result"]
    assert result.row_count == 2  # South + East in the sample data
    assert set(result.columns) == {"region", "revenue"}
    assert update["messages"][0].content == "retrieved 2 rows. Columns: region, revenue"


def test_unknown_entities_skips_database(initialized_engine: Engine):
    """An unidentifiable question sets the error and never touches the DB."""
    tool = _pipeline(
        initialized_engine,
        [],
        SQLGenerationOutput(sql="", explanation="no entities", is_identifiable=False),
    )
    update = _run(tool, question="show dragon sales by galaxy")
    assert update["error_message"] == "Unable to identify requested entities."
    assert update["query_result"] is None


def test_execution_retry_recovers(initialized_engine: Engine):
    """A first bad query (real execution failure) then a valid one → result in state."""
    bad_sql = "SELECT revenue_amount FROM orders"  # column does not exist
    tool = _pipeline(
        initialized_engine, [bad_sql, _REVENUE_SQL], _identifiable(_REVENUE_SQL)
    )
    update = _run(tool)
    assert update["error_message"] is None
    assert update["query_result"].row_count == 2


def test_validation_failure_then_recovers(initialized_engine: Engine):
    """A first non-SELECT attempt is blocked by validation, then a valid SELECT wins."""
    tool = _pipeline(
        initialized_engine,
        ["DELETE FROM orders", _REVENUE_SQL],
        _identifiable(_REVENUE_SQL),
    )
    update = _run(tool)
    assert update["error_message"] is None
    assert update["query_result"].row_count == 2


def test_all_attempts_fail_surfaces_validation_error(initialized_engine: Engine):
    """Repeated non-SELECT attempts exhaust without success → validation error, DB intact."""
    repo = QueryRepository(db_engine=initialized_engine)
    before = repo.execute_select("SELECT COUNT(*) AS n FROM orders").dataframe.iloc[0][
        "n"
    ]
    tool = _pipeline(
        initialized_engine,
        ["DELETE FROM orders", "DROP TABLE orders", "UPDATE orders SET region = 'x'"],
        _identifiable("DELETE FROM orders"),
    )
    update = _run(tool)
    assert update["error_message"] == "Generated query could not be validated."
    assert update["query_result"] is None
    after = repo.execute_select("SELECT COUNT(*) AS n FROM orders").dataframe.iloc[0][
        "n"
    ]
    assert after == before


def test_read_only_guard_blocks_write(initialized_engine: Engine):
    """A DELETE is blocked by validation and the database is left unmodified."""
    repo = QueryRepository(db_engine=initialized_engine)
    before = repo.execute_select("SELECT COUNT(*) AS n FROM orders").dataframe.iloc[0][
        "n"
    ]

    tool = _pipeline(
        initialized_engine, ["DELETE FROM orders"], _identifiable("DELETE FROM orders")
    )
    update = _run(tool)

    assert update["error_message"] == "Generated query could not be validated."
    assert update["query_result"] is None
    after = repo.execute_select("SELECT COUNT(*) AS n FROM orders").dataframe.iloc[0][
        "n"
    ]
    assert after == before  # nothing was deleted


def test_database_error_maps_to_retrieve_message(initialized_engine: Engine):
    """A SELECT that passes validation but fails execution → database error message."""
    bad_sql = "SELECT nonexistent_column FROM orders"
    tool = _pipeline(initialized_engine, [bad_sql], _identifiable(bad_sql))
    update = _run(tool)
    assert update["error_message"] == "Unable to retrieve data at this time."
    assert update["query_result"] is None


def test_empty_result_maps_to_no_data(initialized_engine: Engine):
    """A valid SELECT matching no rows → 'no data found' and cleared result."""
    empty_sql = "SELECT * FROM customers WHERE customer_id = 'NONE'"
    tool = _pipeline(initialized_engine, [empty_sql], _identifiable(empty_sql))
    update = _run(tool)
    assert update["error_message"] == "No data found for the requested query."
    assert update["query_result"] is None
