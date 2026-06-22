"""Tests for app.agents.sql_agent.SqlAgent — the query_database tool mapping.

The inner autonomous agent is replaced with a mock so each test controls the
``invoke`` return (structured_response + query_result + error_type). Covers spec
scenarios under natural-language-to-sql, sql-self-correction-retry, sql-execution,
and tool-message-summary. The inner agent is constructed offline with a dummy
API key (no network at build time).
"""

from unittest.mock import MagicMock, patch

import httpx
import pandas as pd
import pytest
from langchain_google_genai import ChatGoogleGenerativeAI

from app.agents.sql_agent import SqlAgent
from app.schemas.sql_result import QueryResult, SQLGenerationOutput


def _query_database_tool(inner_return: dict):
    """Build a query_database tool whose inner agent returns ``inner_return``."""
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key="test-key")
    agent = SqlAgent(llm, api_base_url="http://testserver", retry_limit=3)
    agent._agent = MagicMock()
    agent._agent.invoke.return_value = inner_return
    return agent.get_tools()[0]


def _invoke(tool, question: str = "show total sales by region") -> dict:
    """Call the tool's underlying function with explicit injected args."""
    command = tool.func(question=question, tool_call_id="call_1", _state={})
    return command.update


def _result(row_count: int = 2) -> QueryResult:
    frame = pd.DataFrame({"region": ["East", "West"], "revenue": [10.0, 20.0]})
    return QueryResult(
        dataframe=frame, columns=["region", "revenue"], row_count=row_count
    )


def test_unidentified_entities_sets_error_and_no_result():
    """is_identifiable=False → standard message, no query_result, no execution."""
    tool = _query_database_tool(
        {
            "structured_response": SQLGenerationOutput(
                sql="", explanation="unknown", is_identifiable=False
            )
        }
    )
    update = _invoke(tool)
    assert update["error_message"] == "Unable to identify requested entities."
    assert update["query_result"] is None


def test_success_sets_result_and_clears_error():
    """A successful run stores query_result, clears error, and uses the template."""
    output = SQLGenerationOutput(
        sql="SELECT region, SUM(sales) FROM ...",
        explanation="by region",
        is_identifiable=True,
    )
    tool = _query_database_tool(
        {"structured_response": output, "query_result": _result(2), "error_type": None}
    )
    update = _invoke(tool)
    assert update["query_result"].row_count == 2
    assert update["error_message"] is None
    assert update["generated_sql"] == output.sql
    assert update["sql_explanation"] == "by region"
    summary = update["messages"][0].content
    assert summary == "retrieved 2 rows. Columns: region, revenue"


def test_validation_failure_maps_to_validation_message():
    """error_type=validation with no result → 'could not be validated' message."""
    output = SQLGenerationOutput(sql="SELECT 1", explanation="x", is_identifiable=True)
    tool = _query_database_tool(
        {"structured_response": output, "error_type": "validation"}
    )
    update = _invoke(tool)
    assert update["error_message"] == "Generated query could not be validated."
    assert update["query_result"] is None
    assert update["generated_sql"] == "SELECT 1"
    assert update["sql_explanation"] == "x"


def test_database_failure_maps_to_database_message():
    """error_type=database with no result → 'unable to retrieve' message."""
    output = SQLGenerationOutput(
        sql="SELECT bad", explanation="x", is_identifiable=True
    )
    tool = _query_database_tool(
        {"structured_response": output, "error_type": "database"}
    )
    update = _invoke(tool)
    assert update["error_message"] == "Unable to retrieve data at this time."
    assert update["query_result"] is None
    assert update["generated_sql"] == "SELECT bad"
    assert update["sql_explanation"] == "x"


def test_empty_result_maps_to_no_data_message():
    """A zero-row result → 'no data found' message, query_result cleared."""
    output = SQLGenerationOutput(sql="SELECT 1", explanation="x", is_identifiable=True)
    tool = _query_database_tool(
        {"structured_response": output, "query_result": _result(0), "error_type": None}
    )
    update = _invoke(tool)
    assert update["error_message"] == "No data found for the requested query."
    assert update["query_result"] is None


def test_retry_limit_sourced_from_settings(monkeypatch):
    """SQL_RETRY_LIMIT (via settings) bounds the inner agent's recursion limit."""
    from app.config import env_config

    monkeypatch.setattr(env_config.settings, "sql_retry_limit", 5)
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key="test-key")
    agent = SqlAgent(llm, api_base_url="http://testserver")  # no explicit retry_limit
    assert agent._retry_limit == 5

    agent._agent = MagicMock()
    output = SQLGenerationOutput(sql="SELECT 1", explanation="x", is_identifiable=True)
    agent._agent.invoke.return_value = {
        "structured_response": output,
        "query_result": _result(2),
        "error_type": None,
    }
    _invoke(agent.get_tools()[0])
    config = agent._agent.invoke.call_args.kwargs["config"]
    assert config["recursion_limit"] == 5 * 2 + 1


def test_retry_limit_defaults_to_settings_value():
    """With SQL_RETRY_LIMIT absent, the limit defaults to settings (3) and is wired."""
    from app.config.env_config import Settings, settings

    assert Settings.model_fields["sql_retry_limit"].default == 3
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key="test-key")
    agent = SqlAgent(llm, api_base_url="http://testserver")
    assert agent._retry_limit == settings.sql_retry_limit


def test_validate_and_execute_calls_query_api():
    """validate_and_execute POSTs to /api/query and reconstructs a QueryResult."""
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key="test-key")
    agent = SqlAgent(llm, api_base_url="http://testserver", retry_limit=1)
    inner_tool = agent._build_validate_and_execute()

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "columns": ["region", "sales"],
        "rows": [{"region": "East", "sales": 100.0}],
        "row_count": 1,
    }

    with patch("app.agents.sql_agent.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.post.return_value = mock_response

        command = inner_tool.func(
            sql="SELECT region, sales FROM order_items",
            tool_call_id="tc1",
        )

    mock_client.post.assert_called_once_with(
        "http://testserver/api/query",
        json={"sql": "SELECT region, sales FROM order_items"},
        timeout=30.0,
    )
    assert command.update["query_result"].row_count == 1
    assert command.update["query_result"].columns == ["region", "sales"]


def test_validate_and_execute_rejects_non_select():
    """validate_and_execute returns a validation error for non-SELECT SQL."""
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key="test-key")
    agent = SqlAgent(llm, api_base_url="http://testserver", retry_limit=1)
    inner_tool = agent._build_validate_and_execute()

    command = inner_tool.func(sql="DROP TABLE orders", tool_call_id="tc2")

    assert command.update["error_type"] == "validation"


@pytest.mark.parametrize(
    "exc",
    [
        httpx.RequestError("conn"),
        httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock()),
    ],
)
def test_validate_and_execute_http_error_maps_to_database_error(exc):
    """Network and HTTP errors from /api/query map to error_type=database."""
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key="test-key")
    agent = SqlAgent(llm, api_base_url="http://testserver", retry_limit=1)
    inner_tool = agent._build_validate_and_execute()

    with patch("app.agents.sql_agent.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.post.side_effect = exc

        command = inner_tool.func(sql="SELECT 1", tool_call_id="tc3")

    assert command.update["error_type"] == "database"
