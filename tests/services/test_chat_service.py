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

from app.schemas.conversation import ConversationTurn
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
    assert not hasattr(resp, "session_history")


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
# Tests — spec: session-history / conversation-context-injection
# ---------------------------------------------------------------------------


def test_graph_invoked_with_empty_conversation_history(
    service: ChatService, mock_graph: MagicMock
) -> None:
    """Spec: first question in a session — graph receives conversation_history=[]."""
    mock_graph.invoke.return_value = _make_state()
    _run(service.ask(_make_request()))

    call_kwargs = mock_graph.invoke.call_args[0][0]
    assert call_kwargs["conversation_history"] == []


def test_conversation_turn_appended_on_success(
    service: ChatService, mock_graph: MagicMock
) -> None:
    """Spec: successful workflow — ConversationTurn appended to in-memory history."""
    mock_graph.invoke.return_value = _make_state(
        generated_sql="SELECT 1", insights=["Insight A"]
    )
    _run(service.ask(_make_request(session="sess-a")))

    history = service._history.get("sess-a", [])
    assert len(history) == 1
    assert isinstance(history[0], ConversationTurn)
    assert history[0].question == "Show monthly sales"
    assert history[0].generated_sql == "SELECT 1"
    assert history[0].insights == ["Insight A"]


def test_conversation_turn_not_appended_on_error(
    service: ChatService, mock_graph: MagicMock
) -> None:
    """Spec: workflow error — errored turn is NOT appended to history."""
    mock_graph.invoke.return_value = _make_state(error_message=_ERR_UNIDENTIFIED)
    _run(service.ask(_make_request(session="sess-err")))

    assert service._history.get("sess-err", []) == []


def test_prior_turn_injected_on_second_call(
    service: ChatService, mock_graph: MagicMock
) -> None:
    """Spec: multi-turn — second call receives prior successful turn in conversation_history."""
    mock_graph.invoke.return_value = _make_state(generated_sql="SELECT 1")
    _run(service.ask(_make_request(question="First question", session="sess-b")))

    mock_graph.invoke.return_value = _make_state(generated_sql="SELECT 2")
    _run(service.ask(_make_request(question="Second question", session="sess-b")))

    second_call_kwargs = mock_graph.invoke.call_args_list[1][0][0]
    history_passed = second_call_kwargs["conversation_history"]
    assert len(history_passed) == 1
    assert history_passed[0].question == "First question"
    assert history_passed[0].generated_sql == "SELECT 1"


def test_cross_session_isolation(service: ChatService, mock_graph: MagicMock) -> None:
    """Spec: cross-session isolation — session A's history never leaks into session B."""
    mock_graph.invoke.return_value = _make_state(generated_sql="SELECT 'A'")
    _run(service.ask(_make_request(question="Question A", session="sess-A")))

    mock_graph.invoke.return_value = _make_state(generated_sql="SELECT 'B'")
    _run(service.ask(_make_request(question="Question B", session="sess-B")))

    b_call_kwargs = mock_graph.invoke.call_args_list[1][0][0]
    history_for_b = b_call_kwargs["conversation_history"]
    assert history_for_b == []
    questions_seen = [t.question for t in history_for_b]
    assert "Question A" not in questions_seen


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
