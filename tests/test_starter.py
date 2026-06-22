"""Tests for the application bootstrap (app/starter.py).

Verifies that ``create_app()`` wires the startup singleton correctly — builds
the LangGraph workflow exactly once and registers both API routers — without
any real LLM calls, DB I/O, or network access.
"""

from unittest.mock import patch

from app.starter import create_app


def test_create_app_builds_graph_once_and_registers_routers() -> None:
    """Spec: startup-singleton / server-starts — graph built once, both routes registered."""
    with (
        patch("app.starter.DatabaseInitializer"),
        patch("app.starter.llm_config"),
        patch("app.starter.QueryService"),
        patch("app.starter.AnalyticsGraph") as mock_ag,
    ):
        app = create_app()

    mock_ag.return_value.build.assert_called_once()

    # FastAPI stores included routers as _IncludedRouter — use url_path_for
    # which raises NoMatchFound if the route is absent.
    assert str(app.url_path_for("submit_question")) == "/api/chat"
    assert str(app.url_path_for("health")) == "/api/health"
