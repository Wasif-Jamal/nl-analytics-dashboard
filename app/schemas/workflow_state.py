"""Workflow state contract for the LangGraph pipeline.

Minimal TypedDict for issue #1 (SQL generation). Later issues extend this
with their own fields (query_result, chart_config, insights, followup_questions).
"""

from typing import Optional

from typing_extensions import TypedDict


class WorkflowState(TypedDict):
    """State passed between LangGraph nodes.

    Attributes:
        question: The original natural-language question from the user.
        generated_sql: The SELECT statement produced by SqlGenerationNode.
        sql_explanation: Plain-English description of the generated query.
        error_message: Standard FRS §10 error string; None when no error.
    """

    question: str
    generated_sql: str
    sql_explanation: str
    error_message: Optional[str]


def initial_state(question: str) -> WorkflowState:
    """Return a fresh WorkflowState for a new question.

    Args:
        question: The natural-language question submitted by the user.

    Returns:
        A WorkflowState with all fields initialised to empty/None defaults.
    """
    return WorkflowState(
        question=question,
        generated_sql="",
        sql_explanation="",
        error_message=None,
    )
