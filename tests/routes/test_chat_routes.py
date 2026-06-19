"""API-level tests for the chat and health routes.

Uses FastAPI's ``TestClient`` against a minimal app assembled from
``ChatRouter(mock_service)`` + ``health_router``. No DB, no real graph, and
no LLM calls occur. Each test maps to a spec scenario in api-layer-fastapi
(spec: submit-question-endpoint, health-endpoint, request-schema,
error-response-safety).
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.chat_routes import ChatRouter
from app.routes.health import router as health_router
from app.schemas.requests import AnalyticsRequest
from app.schemas.responses import AnalyticsResponse
from app.services.chat_service import ChatService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_service() -> MagicMock:
    svc = MagicMock(spec=ChatService)
    svc.ask = AsyncMock()
    return svc


@pytest.fixture
def client(mock_service: MagicMock) -> TestClient:
    app = FastAPI()
    app.include_router(ChatRouter(mock_service).router)
    app.include_router(health_router)
    return TestClient(app)


def _success_response(question: str = "Show monthly sales") -> AnalyticsResponse:
    return AnalyticsResponse(question=question, session_history=[question])


def _error_response(question: str, msg: str) -> AnalyticsResponse:
    return AnalyticsResponse(question=question, error_message=msg, session_history=[])


# ---------------------------------------------------------------------------
# Tests — spec: submit-question-endpoint
# ---------------------------------------------------------------------------


def test_post_chat_success(client: TestClient, mock_service: MagicMock) -> None:
    """Spec: successful question submission — HTTP 200, question echoed in body."""
    mock_service.ask.return_value = _success_response()
    resp = client.post(
        "/api/chat", json={"question": "Show monthly sales", "session_uuid": "s1"}
    )

    assert resp.status_code == 200
    assert resp.json()["question"] == "Show monthly sales"
    assert resp.json()["error_message"] is None


def test_route_delegates_to_service(
    client: TestClient, mock_service: MagicMock
) -> None:
    """Spec: route contains no business logic — delegates entirely to ChatService."""
    mock_service.ask.return_value = _success_response(question="Q")
    client.post("/api/chat", json={"question": "Q", "session_uuid": "s1"})

    assert mock_service.ask.call_count == 1
    called_request: AnalyticsRequest = mock_service.ask.call_args[0][0]
    assert called_request.question == "Q"
    assert called_request.session_uuid == "s1"


def test_unknown_route_returns_404(client: TestClient) -> None:
    """Spec: request to an unknown route — 404 Not Found."""
    resp = client.get("/api/unknown-path")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests — spec: request-schema (validation)
# ---------------------------------------------------------------------------


def test_missing_question_returns_422(client: TestClient) -> None:
    """Spec: missing required field question — 422 Unprocessable Entity."""
    resp = client.post("/api/chat", json={"session_uuid": "s1"})
    assert resp.status_code == 422


def test_empty_question_returns_422(client: TestClient) -> None:
    """Spec: empty question string — 422 Unprocessable Entity."""
    resp = client.post("/api/chat", json={"question": "", "session_uuid": "s1"})
    assert resp.status_code == 422


def test_missing_session_uuid_returns_422(client: TestClient) -> None:
    """Spec: missing required field session_uuid — 422 Unprocessable Entity."""
    resp = client.post("/api/chat", json={"question": "Q"})
    assert resp.status_code == 422


def test_whitespace_only_question_returns_422(client: TestClient) -> None:
    """Spec: whitespace-only question — 422 Unprocessable Entity (non-blank rule)."""
    resp = client.post("/api/chat", json={"question": "   ", "session_uuid": "s1"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Tests — spec: health-endpoint
# ---------------------------------------------------------------------------


def test_health_returns_ok(client: TestClient) -> None:
    """Spec: health check — HTTP 200, body {\"status\": \"ok\"}."""
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Tests — spec: error-response-safety
# ---------------------------------------------------------------------------


def test_workflow_error_is_http_200(
    client: TestClient, mock_service: MagicMock
) -> None:
    """Spec: workflow/backend error — HTTP 200 with error_message in body."""
    mock_service.ask.return_value = _error_response(
        "Q", "Unable to identify requested entities."
    )
    resp = client.post("/api/chat", json={"question": "Q", "session_uuid": "s1"})

    assert resp.status_code == 200
    assert "Unable to identify requested entities." in resp.json()["error_message"]


def test_session_history_returned_in_response(
    client: TestClient, mock_service: MagicMock
) -> None:
    """Spec: response schema — session_history list is present in the payload."""
    mock_service.ask.return_value = AnalyticsResponse(
        question="Q",
        session_history=["prev Q", "Q"],
    )
    resp = client.post("/api/chat", json={"question": "Q", "session_uuid": "s1"})

    assert resp.status_code == 200
    assert resp.json()["session_history"] == ["prev Q", "Q"]


def test_no_data_error_propagated_through_route(
    client: TestClient, mock_service: MagicMock
) -> None:
    """FRS §10 string 3 — 'No data found' message reaches caller as HTTP 200."""
    mock_service.ask.return_value = _error_response(
        "Q", "No data found for the requested query."
    )
    resp = client.post("/api/chat", json={"question": "Q", "session_uuid": "s1"})

    assert resp.status_code == 200
    assert resp.json()["error_message"] == "No data found for the requested query."


def test_validation_error_propagated_through_route(
    client: TestClient, mock_service: MagicMock
) -> None:
    """FRS §10 string 2 — 'Generated query could not be validated' reaches caller as HTTP 200."""
    mock_service.ask.return_value = _error_response(
        "Q", "Generated query could not be validated."
    )
    resp = client.post("/api/chat", json={"question": "Q", "session_uuid": "s1"})

    assert resp.status_code == 200
    assert resp.json()["error_message"] == "Generated query could not be validated."
