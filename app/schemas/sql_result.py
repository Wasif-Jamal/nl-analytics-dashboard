"""Pydantic contract for SQL generation output.

Exchanged between SqlAgent and SqlGenerationNode. Agents communicate
via typed schemas only — never unstructured text (AGENTS.md §8).
"""

from pydantic import BaseModel


class SQLGenerationOutput(BaseModel):
    """Structured output from the SQL generation LLM call.

    Attributes:
        sql: The generated SELECT statement; empty string when is_identifiable=False.
        explanation: Plain-English description of the query, or reason for failure.
        is_identifiable: False when the question references entities not in the schema.
    """

    sql: str
    explanation: str
    is_identifiable: bool = True
