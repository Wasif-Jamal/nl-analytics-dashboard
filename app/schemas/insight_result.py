"""Pydantic contracts for the insight generation pipeline.

``InsightOutput`` is the structured response the insight agent produces when
analyzing query results. It represents 3–5 actionable, data-grounded insights
derived from the returned rows. Agents communicate via typed schemas only —
never unstructured text (AGENTS.md §8).
"""

from pydantic import BaseModel


class InsightOutput(BaseModel):
    """Structured output from the insight generation LLM call.

    Attributes:
        insights: List of 3–5 plain-English insight strings, each a single clear
            sentence describing a notable pattern, leader/laggard, concentration,
            peak, significant change, or anomaly visible in the query results.
            Each insight is grounded only in facts from the returned data.
    """

    insights: list[str]
