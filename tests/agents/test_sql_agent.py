"""Unit tests for app.tools.sql_tools.SqlTools and app.agents.sql_agent.SqlAgent.

Tests each of the four internal tools directly via their ``.func`` attribute
(bypassing LangChain's tool-calling wrapper), and verifies that ``SqlAgent``
wires the retry limit from settings into the compiled agent config.

All network calls (``httpx.Client``) and LLM calls
(``llm.with_structured_output``) are mocked; no real API key or server is
needed.

Covers spec scenarios: natural-language-to-sql, read-only-validation,
sql-execution, tool-message-summary, execute-sql-terminal,
handle-unidentifiable, env-configuration, sql-tools-class.
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest
from langchain_google_genai import ChatGoogleGenerativeAI

from app.agents.sql_agent import SqlAgent
from app.schemas.sql_result import QueryResult, SQLGenerationOutput
from app.tools.sql_tools import SqlTools

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_API_BASE = "http://testserver"
_SELECT_SQL = "SELECT region, SUM(sales) AS sales FROM order_items GROUP BY region"


def _make_tools(mock_llm=None) -> SqlTools:
    """Return a SqlTools instance, optionally with a mocked LLM."""
    llm = mock_llm or ChatGoogleGenerativeAI(
        model="gemini-2.0-flash", google_api_key="test-key"
    )
    return SqlTools(llm=llm, api_base_url=_API_BASE)


def _mock_http_response(
    columns: list[str],
    rows: list[dict],
    row_count: int,
    status_code: int = 200,
) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {
        "columns": columns,
        "rows": rows,
        "row_count": row_count,
    }
    if status_code != 200:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            str(status_code), request=MagicMock(), response=MagicMock()
        )
    return resp


def _patch_http(mock_response: MagicMock):
    """Context manager that patches httpx.Client inside sql_tools."""
    mock_cls = MagicMock()
    mock_cls.return_value.__enter__.return_value.post.return_value = mock_response
    return patch("app.tools.sql_tools.httpx.Client", mock_cls), mock_cls


# ---------------------------------------------------------------------------
# generate_sql
# ---------------------------------------------------------------------------


def test_generate_sql_identifiable():
    """generate_sql returns SQLGenerationOutput with is_identifiable=True."""
    mock_chain = MagicMock()
    mock_chain.invoke.return_value = SQLGenerationOutput(
        sql=_SELECT_SQL, explanation="sales by region", is_identifiable=True
    )
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_chain

    tools = _make_tools(mock_llm)
    result = tools.generate_sql.func(question="show total sales by region")

    assert isinstance(result, SQLGenerationOutput)
    assert result.is_identifiable is True
    assert result.sql == _SELECT_SQL
    mock_llm.with_structured_output.assert_called_once_with(SQLGenerationOutput)


def test_generate_sql_unidentifiable():
    """generate_sql returns is_identifiable=False for unknown-entity questions."""
    mock_chain = MagicMock()
    mock_chain.invoke.return_value = SQLGenerationOutput(
        sql="", explanation="unknown entities", is_identifiable=False
    )
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_chain

    tools = _make_tools(mock_llm)
    result = tools.generate_sql.func(question="show dragon sales by galaxy")

    assert result.is_identifiable is False


# ---------------------------------------------------------------------------
# validate_sql
# ---------------------------------------------------------------------------


def test_validate_sql_valid_select():
    """validate_sql returns {valid: True} for a SELECT statement."""
    tools = _make_tools()
    result = tools.validate_sql.func(sql="SELECT 1")
    assert result == {"valid": True}


def test_validate_sql_rejects_write():
    """validate_sql returns valid=False with a reason for non-SELECT SQL."""
    tools = _make_tools()
    for bad_sql in [
        "DROP TABLE orders",
        "DELETE FROM orders",
        "INSERT INTO orders VALUES (1)",
    ]:
        result = tools.validate_sql.func(sql=bad_sql)
        assert result["valid"] is False
        assert "reason" in result


# ---------------------------------------------------------------------------
# execute_sql
# ---------------------------------------------------------------------------


def test_execute_sql_success():
    """execute_sql writes result fields and clears error_message on success."""
    tools = _make_tools()
    mock_resp = _mock_http_response(
        columns=["region", "sales"],
        rows=[{"region": "East", "sales": 100.0}],
        row_count=1,
    )
    ctx, _ = _patch_http(mock_resp)
    with ctx:
        command = tools.execute_sql.func(
            sql=_SELECT_SQL,
            explanation="sales by region",
            tool_call_id="tc1",
        )

    u = command.update
    assert u["error_message"] is None
    assert u["generated_sql"] == _SELECT_SQL
    assert u["sql_explanation"] == "sales by region"
    assert isinstance(u["query_result"], QueryResult)
    assert u["query_result"].row_count == 1
    assert u["messages"][0].content == "retrieved 1 rows. Columns: region, sales"


def test_execute_sql_zero_rows():
    """execute_sql sets _ERR_EMPTY and clears query_result on a 0-row result."""
    tools = _make_tools()
    mock_resp = _mock_http_response(columns=["region"], rows=[], row_count=0)
    ctx, _ = _patch_http(mock_resp)
    with ctx:
        command = tools.execute_sql.func(
            sql=_SELECT_SQL, explanation="x", tool_call_id="tc2"
        )

    u = command.update
    assert u["error_message"] == "No data found for the requested query."
    assert u["query_result"] is None


def test_execute_sql_defense_in_depth_blocks_write():
    """execute_sql blocks non-SELECT SQL without calling POST /api/query."""
    tools = _make_tools()
    with patch("app.tools.sql_tools.httpx.Client") as mock_cls:
        command = tools.execute_sql.func(
            sql="DELETE FROM orders", explanation="", tool_call_id="tc3"
        )
        mock_cls.assert_not_called()

    assert command.update["error_message"] == "Generated query could not be validated."
    assert command.update["query_result"] is None


@pytest.mark.parametrize(
    "exc",
    [
        httpx.RequestError("conn"),
        httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock()),
    ],
)
def test_execute_sql_http_error(exc):
    """Network and HTTP errors map to _ERR_DATABASE; query_result is None."""
    tools = _make_tools()
    with patch("app.tools.sql_tools.httpx.Client") as mock_cls:
        mock_cls.return_value.__enter__.return_value.post.side_effect = exc
        command = tools.execute_sql.func(
            sql=_SELECT_SQL, explanation="x", tool_call_id="tc4"
        )

    assert command.update["error_message"] == "Unable to retrieve data at this time."
    assert command.update["query_result"] is None


# ---------------------------------------------------------------------------
# handle_unidentifiable
# ---------------------------------------------------------------------------


def test_handle_unidentifiable():
    """handle_unidentifiable sets _ERR_UNIDENTIFIED and clears sql/result fields."""
    tools = _make_tools()
    command = tools.handle_unidentifiable.func(tool_call_id="tc5")

    u = command.update
    assert u["error_message"] == "Unable to identify requested entities."
    assert u["query_result"] is None
    assert u["generated_sql"] is None
    assert u["messages"][0].content == "Unable to identify requested entities."


# ---------------------------------------------------------------------------
# SqlAgent — retry limit wiring
# ---------------------------------------------------------------------------


def test_retry_limit_sourced_from_settings(monkeypatch):
    """SQL_RETRY_LIMIT env var is read and stored on SqlAgent._retry_limit."""
    from app.config import env_config

    monkeypatch.setattr(env_config.settings, "sql_retry_limit", 5)
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key="test-key")
    agent = SqlAgent(llm, api_base_url=_API_BASE)
    assert agent._retry_limit == 5


def test_retry_limit_defaults_to_settings_value():
    """Without explicit retry_limit, SqlAgent reads the default (3) from settings."""
    from app.config.env_config import Settings, settings

    assert Settings.model_fields["sql_retry_limit"].default == 3
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key="test-key")
    agent = SqlAgent(llm, api_base_url=_API_BASE)
    assert agent._retry_limit == settings.sql_retry_limit


def test_sql_tools_passed_to_create_agent():
    """SqlAgent builds a compiled _agent from the four SqlTools closures."""
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key="test-key")
    agent = SqlAgent(llm, api_base_url=_API_BASE, retry_limit=1)
    assert agent._agent is not None
