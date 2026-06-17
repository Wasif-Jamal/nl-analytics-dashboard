"""Tests for app.orchestration.nodes.sql_generation_node.SqlGenerationNode.

Spec scenarios covered:
  - "Valid business question": success path sets generated_sql + sql_explanation
  - "Unknown schema entities": is_identifiable=False sets error_message, sql stays empty
  - "LLM call fails": exception sets error_message, node does not re-raise
"""

from unittest.mock import MagicMock

from app.orchestration.nodes.sql_generation_node import SqlGenerationNode
from app.schemas.sql_result import SQLGenerationOutput
from app.schemas.workflow_state import initial_state


def _make_node(output: SQLGenerationOutput | Exception) -> SqlGenerationNode:
    """Return a SqlGenerationNode whose agent is mocked to return output or raise."""
    mock_agent = MagicMock()
    if isinstance(output, Exception):
        mock_agent.generate.side_effect = output
    else:
        mock_agent.generate.return_value = output
    return SqlGenerationNode(agent=mock_agent)


def test_node_success_sets_sql_and_explanation():
    """Spec scenario: Valid business question — state gets generated_sql and sql_explanation."""
    node = _make_node(
        SQLGenerationOutput(
            sql="SELECT * FROM orders",
            explanation="Returns all order records.",
            is_identifiable=True,
        )
    )
    result = node(initial_state("Show all orders"))
    assert result["generated_sql"] == "SELECT * FROM orders"
    assert result["sql_explanation"] == "Returns all order records."
    assert result["error_message"] is None


def test_node_unidentifiable_sets_error_message():
    """Spec scenario: Unknown schema entities — error_message set, generated_sql stays empty."""
    node = _make_node(
        SQLGenerationOutput(
            sql="", explanation="Unknown entities.", is_identifiable=False
        )
    )
    result = node(initial_state("Show dragon sales by galaxy"))
    assert result["error_message"] == "Unable to identify requested entities."
    assert result["generated_sql"] == ""


def test_node_exception_sets_error_message():
    """Spec scenario: LLM call fails — error_message set, generated_sql stays empty, no re-raise."""
    node = _make_node(RuntimeError("LLM quota exceeded"))
    result = node(initial_state("Show total sales"))
    assert result["error_message"] == "Unable to identify requested entities."
    assert result["generated_sql"] == ""
