"""Pydantic contracts for the SQL pipeline.

``SQLGenerationOutput`` is the structured response the SQL agent produces;
``QueryResult`` wraps the executed query's data plus metadata. Agents and
layers communicate via typed schemas only — never unstructured text (AGENTS.md §8).
"""

import pandas as pd
from pydantic import BaseModel, ConfigDict


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


class QueryResult(BaseModel):
    """Result of a successfully executed read-only ``SELECT`` query.

    Stored in ``WorkflowState.query_result`` as in-process execution state; holds
    a native DataFrame for efficient downstream analytics and is therefore not
    JSON-serializable.

    Attributes:
        dataframe: The rows returned by the query.
        columns: Column names, in result order.
        row_count: Number of rows returned.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    dataframe: pd.DataFrame
    columns: list[str]
    row_count: int
