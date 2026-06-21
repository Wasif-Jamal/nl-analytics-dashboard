"""Pydantic response schemas for the FastAPI API layer.

``AnalyticsResponse`` is the full contract returned by ``POST /api/chat``.
All analytics fields are ``Optional`` so the schema is stable from day one;
future agents (visualization, insights, follow-up) populate them as they land.
``HealthResponse`` is returned by ``GET /api/health``.
"""

from typing import Optional

from pydantic import BaseModel


class AnalyticsResponse(BaseModel):
    """Response payload for the submit-question endpoint.

    All analytics fields default to ``None``; they are populated by the
    relevant agents as those issues land. ``error_message`` is set (and
    analytics fields left ``None``) when the workflow or transport fails.
    ``session_history`` is always returned and reflects successfully answered
    questions for the session, ordered oldest-first.

    Attributes:
        question: Echo of the submitted question.
        generated_sql: SQL produced by the SQL agent; ``None`` on error.
        sql_explanation: Plain-English explanation of the SQL; ``None`` on error.
        query_result: Serialized rows from ``QueryResult.dataframe.to_dict(orient="records")``;
            ``None`` when no data was returned or an error occurred.
        columns: Ordered column names from ``QueryResult.columns``; ``None`` when
            ``query_result`` is ``None``.
        row_count: Row count from ``QueryResult.row_count``; ``None`` when
            ``query_result`` is ``None``.
        chart_config: Visualization config (populated by issue #5).
        insights: Data-grounded insights (populated by issue #6).
        followup_questions: Suggested follow-up questions (populated by issue #7).
        error_message: Standard FRS §10 message on failure; ``None`` on success.
        session_history: Ordered list of successfully answered questions for
            this session (never includes errored questions).
    """

    question: str
    generated_sql: Optional[str] = None
    sql_explanation: Optional[str] = None
    query_result: Optional[list[dict]] = None
    columns: Optional[list[str]] = None
    row_count: Optional[int] = None
    chart_config: Optional[dict] = None
    insights: Optional[list[str]] = None
    followup_questions: Optional[list[str]] = None
    error_message: Optional[str] = None
    session_history: list[str] = []


class HealthResponse(BaseModel):
    """Response payload for the health-check endpoint.

    Attributes:
        status: Always ``"ok"`` when the server is reachable.
    """

    status: str
