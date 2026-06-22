"""Pydantic request schemas for the FastAPI API layer.

``AnalyticsRequest`` is the validated inbound payload for ``POST /api/chat``.
FastAPI validates every request against this model before the route handler
runs, returning ``422 Unprocessable Entity`` automatically on invalid input.
"""

from pydantic import BaseModel, Field, field_validator


class QueryRequest(BaseModel):
    """Inbound payload for the execute-query endpoint.

    Attributes:
        sql: The SELECT statement to execute. Must be non-empty.
    """

    sql: str = Field(..., min_length=1)


class AnalyticsRequest(BaseModel):
    """Inbound payload for the submit-question endpoint.

    Attributes:
        question: The user's natural-language question. Must be non-empty and
            non-blank (whitespace-only strings are rejected).
        session_uuid: Client-generated session identifier used to maintain
            per-session question history in the Chat Service.
    """

    question: str = Field(..., min_length=1)
    session_uuid: str

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, v: str) -> str:
        """Reject questions that are whitespace-only after stripping."""
        if not v.strip():
            raise ValueError("question must not be blank")
        return v
