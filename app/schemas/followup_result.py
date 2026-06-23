"""Pydantic contracts for the suggested follow-up questions pipeline.

``FollowupOutput`` is the structured response the follow-up agent produces when
generating suggested next questions. It represents 1–3 follow-up question
strings, each grounded in the current query result and independently executable
as a new database query. Agents communicate via typed schemas only —
never unstructured text (AGENTS.md §8).
"""

from pydantic import BaseModel, Field


class FollowupOutput(BaseModel):
    """Structured output from the follow-up question generation LLM call.

    Attributes:
        followup_questions: List of 1–3 plain-English follow-up question
            strings, each independently executable as a new database query. Each
            question is grounded in the current query result — drilling down into
            a subset, comparing cohorts, extending the trend, or exploring a
            detail suggested by the returned data. Questions are concise and
            actionable; no filler or fabricated prompts are included.
    """

    followup_questions: list[str] = Field(..., min_length=1)
