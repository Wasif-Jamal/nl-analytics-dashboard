"""Unit tests for ChatService (app/services/chat_service.py).

All tests mock the compiled graph via MagicMock so no LLM call or DB
interaction occurs. ``ask()`` is a coroutine; tests invoke it with
``asyncio.run()`` — no additional pytest-asyncio dependency required.
Each test maps 1:1 to a spec scenario in the api-layer-fastapi spec
(spec: chat-service-workflow-bridge, session-history, error-response-safety)
and the streamlit-ui spec (spec: response-schema).
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from app.schemas.requests import AnalyticsRequest
from app.schemas.sql_result import QueryResult
from app.services.chat_service import ChatService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ERR_UNIDENTIFIED = "Unable to identify requested entities."
_ERR_DATABASE = "Unable to retrieve data at this time."


def _make_request(
    question: str = "Show monthly sales", session: str = "sess-1"
) -> AnalyticsRequest:
    return AnalyticsRequest(question=question, session_uuid=session)


def _make_state(**overrides) -> dict:
    """Return a minimal WorkflowState-shaped dict; overrides applied on top."""
    base = {
        "generated_sql": None,
        "sql_explanation": None,
        "query_result": None,
        "chart_config": None,
        "insights": None,
        "followup_questions": None,
        "error_message": None,
    }
    base.update(overrides)
    return base


def _run(coro):
    """Run a coroutine synchronously (no pytest-asyncio needed)."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_graph() -> MagicMock:
    return MagicMock()


@pytest.fixture
def service(mock_graph: MagicMock) -> ChatService:
    return ChatService(mock_graph)


# ---------------------------------------------------------------------------
# Tests — spec: chat-service-workflow-bridge
# ---------------------------------------------------------------------------


def test_success_returns_populated_response(
    service: ChatService, mock_graph: MagicMock
) -> None:
    """Spec: successful workflow invocation — response fields mapped from state."""
    mock_graph.invoke.return_value = _make_state(
        generated_sql="SELECT 1",
        sql_explanation="Counts everything.",
    )
    resp = _run(service.ask(_make_request()))

    assert resp.error_message is None
    assert resp.generated_sql == "SELECT 1"
    assert resp.sql_explanation == "Counts everything."
    assert resp.question == "Show monthly sales"


def test_workflow_error_propagated(service: ChatService, mock_graph: MagicMock) -> None:
    """Spec: workflow sets error_message — response carries the standard message."""
    mock_graph.invoke.return_value = _make_state(error_message=_ERR_UNIDENTIFIED)
    resp = _run(service.ask(_make_request()))

    assert resp.error_message == _ERR_UNIDENTIFIED
    assert resp.generated_sql is None


def test_exception_returns_safe_error(
    service: ChatService, mock_graph: MagicMock
) -> None:
    """Spec: unhandled exception from graph — HTTP 200 safe error message only."""
    mock_graph.invoke.side_effect = RuntimeError("internal boom")
    resp = _run(service.ask(_make_request()))

    assert resp.error_message == _ERR_DATABASE


def test_exception_error_message_is_standard_string(
    service: ChatService, mock_graph: MagicMock
) -> None:
    """Spec: error-response-safety — raw exception text must not leak."""
    mock_graph.invoke.side_effect = ValueError("secret internal detail")
    resp = _run(service.ask(_make_request()))

    assert resp.error_message == _ERR_DATABASE
    assert "secret" not in (resp.error_message or "")


# ---------------------------------------------------------------------------
# Tests — spec: session-history
# ---------------------------------------------------------------------------


def test_first_question_appended_to_history(
    service: ChatService, mock_graph: MagicMock
) -> None:
    """Spec: first question in a new session — history contains exactly one entry."""
    mock_graph.invoke.return_value = _make_state()
    resp = _run(service.ask(_make_request(question="Q1", session="new-sess")))

    assert resp.session_history == ["Q1"]


def test_subsequent_questions_accumulate(
    service: ChatService, mock_graph: MagicMock
) -> None:
    """Spec: subsequent questions in the same session — both appended in order."""
    mock_graph.invoke.return_value = _make_state()
    _run(service.ask(_make_request(question="Q1", session="s")))
    resp = _run(service.ask(_make_request(question="Q2", session="s")))

    assert resp.session_history == ["Q1", "Q2"]


def test_workflow_error_not_appended_to_history(
    service: ChatService, mock_graph: MagicMock
) -> None:
    """Spec: errored question is not appended — history unchanged on error."""
    mock_graph.invoke.return_value = _make_state(error_message=_ERR_UNIDENTIFIED)
    resp = _run(service.ask(_make_request(question="bad Q", session="s2")))

    assert resp.session_history == []


def test_error_does_not_pollute_existing_history(
    service: ChatService, mock_graph: MagicMock
) -> None:
    """Spec: one success then one workflow error — history has only the first."""
    mock_graph.invoke.return_value = _make_state()
    _run(service.ask(_make_request(question="Good Q", session="s3")))

    mock_graph.invoke.return_value = _make_state(error_message=_ERR_UNIDENTIFIED)
    resp = _run(service.ask(_make_request(question="Bad Q", session="s3")))

    assert resp.session_history == ["Good Q"]


def test_exception_does_not_append_to_history(
    service: ChatService, mock_graph: MagicMock
) -> None:
    """Spec: unhandled exception — question not appended; history unchanged."""
    mock_graph.invoke.side_effect = RuntimeError("boom")
    resp = _run(service.ask(_make_request(question="crash Q", session="s4")))

    assert resp.session_history == []


# ---------------------------------------------------------------------------
# Tests — spec: error-response-safety (FRS §10 allowlist)
# ---------------------------------------------------------------------------

_ERR_NO_DATA = "No data found for the requested query."
_ERR_INVALID_SQL = "Generated query could not be validated."


def test_no_data_error_propagated(service: ChatService, mock_graph: MagicMock) -> None:
    """FRS §10 string 3 — 'No data found' message propagated from graph state."""
    mock_graph.invoke.return_value = _make_state(error_message=_ERR_NO_DATA)
    resp = _run(service.ask(_make_request()))

    assert resp.error_message == _ERR_NO_DATA


def test_validation_error_propagated(
    service: ChatService, mock_graph: MagicMock
) -> None:
    """FRS §10 string 2 — 'Generated query could not be validated' propagated from graph state."""
    mock_graph.invoke.return_value = _make_state(error_message=_ERR_INVALID_SQL)
    resp = _run(service.ask(_make_request()))

    assert resp.error_message == _ERR_INVALID_SQL


def test_non_allowlist_error_replaced_with_database_error(
    service: ChatService, mock_graph: MagicMock
) -> None:
    """Spec: error-response-safety — non-standard graph error_message replaced with safe string."""
    mock_graph.invoke.return_value = _make_state(
        error_message="internal graph failure: unexpected token"
    )
    resp = _run(service.ask(_make_request()))

    assert resp.error_message == _ERR_DATABASE
    assert "internal graph failure" not in (resp.error_message or "")


# ---------------------------------------------------------------------------
# Tests — spec: response-schema (streamlit-ui — query_result serialization)
# ---------------------------------------------------------------------------


def test_query_result_serialized_in_response(
    service: ChatService, mock_graph: MagicMock
) -> None:
    """Spec: successful workflow — query_result serialized to list[dict] in response."""
    qr = QueryResult(
        rows=[{"month": "Jan", "sales": 1000}],
        columns=["month", "sales"],
        row_count=1,
    )
    mock_graph.invoke.return_value = _make_state(query_result=qr)
    resp = _run(service.ask(_make_request()))

    assert resp.query_result == [{"month": "Jan", "sales": 1000}]
    assert resp.columns == ["month", "sales"]
    assert resp.row_count == 1


def test_query_result_none_when_absent(
    service: ChatService, mock_graph: MagicMock
) -> None:
    """Spec: workflow error path — query_result, columns, row_count all None in response."""
    mock_graph.invoke.return_value = _make_state(query_result=None)
    resp = _run(service.ask(_make_request()))

    assert resp.query_result is None
    assert resp.columns is None
    assert resp.row_count is None
