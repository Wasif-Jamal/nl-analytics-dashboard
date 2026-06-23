"""API-level tests for the query route.

Uses FastAPI's ``TestClient`` against a minimal app assembled from
``QueryRouter(mock_service)``. No DB or real SQL execution occurs.
"""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.query_routes import QueryRouter
from app.schemas.sql_result import QueryResult
from app.services.sql_service import QueryService


@pytest.fixture
def mock_service() -> MagicMock:
    return MagicMock(spec=QueryService)


@pytest.fixture
def client(mock_service: MagicMock) -> TestClient:
    app = FastAPI()
    app.include_router(QueryRouter(mock_service).router)
    return TestClient(app)


def _make_result(rows: list[dict], columns: list[str]) -> QueryResult:
    return QueryResult(rows=rows, columns=columns, row_count=len(rows))


def test_post_query_success(client: TestClient, mock_service: MagicMock) -> None:
    """Valid SELECT returns 200 with columns, rows, and row_count."""
    mock_service.run_query.return_value = _make_result(
        [{"region": "East", "sales": 100.0}], ["region", "sales"]
    )
    resp = client.post(
        "/api/query", json={"sql": "SELECT region, sales FROM order_items"}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["columns"] == ["region", "sales"]
    assert body["rows"] == [{"region": "East", "sales": 100.0}]
    assert body["row_count"] == 1


def test_post_query_delegates_to_service(
    client: TestClient, mock_service: MagicMock
) -> None:
    """Route contains no business logic — delegates entirely to QueryService."""
    mock_service.run_query.return_value = _make_result([], [])
    client.post("/api/query", json={"sql": "SELECT 1"})

    mock_service.run_query.assert_called_once_with("SELECT 1")


def test_post_query_rejects_non_select(
    client: TestClient, mock_service: MagicMock
) -> None:
    """Non-SELECT SQL is rejected with HTTP 400 before reaching the service."""
    resp = client.post("/api/query", json={"sql": "DROP TABLE orders"})

    assert resp.status_code == 400
    mock_service.run_query.assert_not_called()


def test_post_query_rejects_insert(client: TestClient, mock_service: MagicMock) -> None:
    """INSERT is rejected with HTTP 400."""
    resp = client.post("/api/query", json={"sql": "INSERT INTO orders VALUES (1)"})

    assert resp.status_code == 400


def test_post_query_missing_sql_returns_422(client: TestClient) -> None:
    """Missing sql field returns 422 Unprocessable Entity."""
    resp = client.post("/api/query", json={})
    assert resp.status_code == 422


def test_post_query_empty_sql_returns_422(client: TestClient) -> None:
    """Empty sql string returns 422 Unprocessable Entity."""
    resp = client.post("/api/query", json={"sql": ""})
    assert resp.status_code == 422
