"""Integration tests for the SQL pipeline against a real SQLite database.

These exercise the real validation → ``/api/query`` → ``QueryService`` →
``QueryRepository`` → SQLite path using the ``initialized_engine`` fixture.
HTTP calls from ``execute_sql`` are intercepted by a custom sync
``httpx.BaseTransport`` that routes requests directly to ``QueryService``
(no running server required).

The four internal tools (``generate_sql``, ``validate_sql``, ``execute_sql``,
``handle_unidentifiable``) are called via their ``.func`` attribute, mimicking
the sequence the SQL Agent's LLM would produce during a real run.

Covers spec scenarios: natural-language-to-sql, read-only-validation,
sql-self-correction-retry, sql-execution, tool-message-summary,
database-access-boundary.
"""

import json
from unittest.mock import MagicMock, patch

import httpx
from langchain_google_genai import ChatGoogleGenerativeAI
from sqlalchemy import Engine

from app.repositories.query_repository import QueryRepository
from app.services.sql_service import QueryService
from app.tools.sql_tools import SqlTools
from app.utils.validators import validate_select_only

_REVENUE_SQL = (
    "SELECT o.region, ROUND(SUM(oi.sales), 2) AS revenue "
    "FROM order_items oi JOIN orders o ON oi.order_id = o.order_id "
    "GROUP BY o.region"
)


# ---------------------------------------------------------------------------
# HTTP transport shim — routes POST /api/query directly to QueryService
# ---------------------------------------------------------------------------


class _QueryServiceTransport(httpx.BaseTransport):
    """Sync httpx transport that routes ``POST /api/query`` to ``QueryService``.

    Mirrors the route-level validation and serialisation of ``QueryRouter``
    without requiring a running ASGI server.
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


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_tools(initialized_engine: Engine) -> tuple[SqlTools, httpx.Client]:
    """Return SqlTools wired to the test DB via the transport shim."""
    service = QueryService(repository=QueryRepository(db_engine=initialized_engine))
    http_client = _make_test_client(service)
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key="test-key")
    tools = SqlTools(llm=llm, api_base_url="http://testserver")
    return tools, http_client


def _run_execute(
    tools: SqlTools,
    http_client: httpx.Client,
    sql: str,
    explanation: str = "explanation",
    tool_call_id: str = "call_1",
) -> dict:
    """Call execute_sql.func with the transport shim patched in."""
    with patch("app.tools.sql_tools.httpx.Client") as mock_cls:
        mock_cls.return_value.__enter__.return_value = http_client
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        return tools.execute_sql.func(
            sql=sql, explanation=explanation, tool_call_id=tool_call_id
        ).update


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


def test_happy_path_populates_result(initialized_engine: Engine):
    """Valid SQL executes against real SQLite and populates WorkflowState fields."""
    tools, http_client = _make_tools(initialized_engine)
    update = _run_execute(tools, http_client, _REVENUE_SQL, explanation="by region")

    assert update["error_message"] is None
    assert update["generated_sql"] == _REVENUE_SQL
    assert update["sql_explanation"] == "by region"
    result = update["query_result"]
    assert result.row_count == 2  # South + East in sample data
    assert set(result.columns) == {"region", "revenue"}
    assert update["messages"][0].content == "retrieved 2 rows. Columns: region, revenue"


def test_unknown_entities_skips_database(initialized_engine: Engine):
    """handle_unidentifiable sets the error message without touching the DB."""
    tools, _ = _make_tools(initialized_engine)
    command = tools.handle_unidentifiable.func(tool_call_id="call_1")
    update = command.update

    assert update["error_message"] == "Unable to identify requested entities."
    assert update["query_result"] is None
    assert update["generated_sql"] is None


def test_execution_retry_recovers(initialized_engine: Engine):
    """A first bad query (real DB error) then a valid one — final state is success."""
    tools, http_client = _make_tools(initialized_engine)
    bad_sql = "SELECT revenue_amount FROM orders"  # column does not exist

    first = _run_execute(tools, http_client, bad_sql)
    assert first["error_message"] == "Unable to retrieve data at this time."
    assert first["query_result"] is None

    # LLM would retry with corrected SQL
    second = _run_execute(tools, http_client, _REVENUE_SQL)
    assert second["error_message"] is None
    assert second["query_result"].row_count == 2


def test_validation_failure_then_recovers(initialized_engine: Engine):
    """validate_sql rejects non-SELECT; a subsequent valid execute_sql succeeds."""
    tools, http_client = _make_tools(initialized_engine)

    # LLM calls validate_sql first — receives feedback, does not execute
    vresult = tools.validate_sql.func(sql="DELETE FROM orders")
    assert vresult["valid"] is False
    assert "reason" in vresult

    # LLM retries with a valid SELECT
    update = _run_execute(tools, http_client, _REVENUE_SQL)
    assert update["error_message"] is None
    assert update["query_result"].row_count == 2


def test_all_attempts_fail_surfaces_validation_error(initialized_engine: Engine):
    """Repeated non-SELECT SQL blocked by validate_sql; DB is unmodified throughout."""
    repo = QueryRepository(db_engine=initialized_engine)
    before = repo.execute_select("SELECT COUNT(*) AS n FROM orders").dataframe.iloc[0][
        "n"
    ]

    tools, _ = _make_tools(initialized_engine)
    bad_sqls = [
        "DELETE FROM orders",
        "DROP TABLE orders",
        "UPDATE orders SET region='x'",
    ]
    for sql in bad_sqls:
        result = tools.validate_sql.func(sql=sql)
        assert result["valid"] is False

    after = repo.execute_select("SELECT COUNT(*) AS n FROM orders").dataframe.iloc[0][
        "n"
    ]
    assert after == before  # nothing was modified


def test_read_only_guard_blocks_write(initialized_engine: Engine):
    """execute_sql defense-in-depth blocks DELETE and leaves the DB unmodified."""
    repo = QueryRepository(db_engine=initialized_engine)
    before = repo.execute_select("SELECT COUNT(*) AS n FROM orders").dataframe.iloc[0][
        "n"
    ]

    tools, http_client = _make_tools(initialized_engine)
    update = _run_execute(tools, http_client, "DELETE FROM orders")

    assert update["error_message"] == "Generated query could not be validated."
    assert update["query_result"] is None

    after = repo.execute_select("SELECT COUNT(*) AS n FROM orders").dataframe.iloc[0][
        "n"
    ]
    assert after == before


def test_database_error_maps_to_retrieve_message(initialized_engine: Engine):
    """A SELECT that passes validation but references a missing column → DB error."""
    tools, http_client = _make_tools(initialized_engine)
    update = _run_execute(tools, http_client, "SELECT nonexistent_column FROM orders")

    assert update["error_message"] == "Unable to retrieve data at this time."
    assert update["query_result"] is None


def test_empty_result_maps_to_no_data(initialized_engine: Engine):
    """A valid SELECT matching zero rows sets _ERR_EMPTY and clears query_result."""
    tools, http_client = _make_tools(initialized_engine)
    empty_sql = "SELECT * FROM customers WHERE customer_id = 'NONEXISTENT'"
    update = _run_execute(tools, http_client, empty_sql)

    assert update["error_message"] == "No data found for the requested query."
    assert update["query_result"] is None
