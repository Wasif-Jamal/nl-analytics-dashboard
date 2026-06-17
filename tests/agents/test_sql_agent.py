"""Tests for app.agents.sql_agent.SqlAgent.

Spec scenarios covered:
  - "Identifiable question": generate() returns SQLGenerationOutput with is_identifiable=True
  - "Unidentifiable question": generate() propagates is_identifiable=False from the LLM
"""

from unittest.mock import MagicMock

from app.agents.sql_agent import SqlAgent
from app.schemas.sql_result import SQLGenerationOutput


def _make_agent(output: SQLGenerationOutput) -> SqlAgent:
    """Return a SqlAgent whose LLM is mocked to return the given output."""
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value.invoke.return_value = output
    return SqlAgent(llm=mock_llm)


def test_generate_returns_sql_generation_output():
    """Spec scenario: Identifiable question — generate() returns a typed SQLGenerationOutput."""
    expected = SQLGenerationOutput(
        sql="SELECT o.region, SUM(oi.sales) FROM order_items oi JOIN orders o ON oi.order_id = o.order_id GROUP BY o.region",
        explanation="Sums sales grouped by region.",
        is_identifiable=True,
    )
    agent = _make_agent(expected)
    result = agent.generate("Show total sales by region")
    assert isinstance(result, SQLGenerationOutput)
    assert result.sql == expected.sql
    assert result.explanation == expected.explanation
    assert result.is_identifiable is True


def test_generate_unidentifiable_question():
    """Spec scenario: Unidentifiable question — generate() propagates is_identifiable=False."""
    expected = SQLGenerationOutput(
        sql="",
        explanation="The question references 'dragon' and 'galaxy' which are not in the schema.",
        is_identifiable=False,
    )
    agent = _make_agent(expected)
    result = agent.generate("Show dragon sales by galaxy")
    assert result.is_identifiable is False
    assert result.sql == ""
    assert result.explanation != ""
