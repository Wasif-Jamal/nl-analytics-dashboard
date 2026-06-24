"""Workflow execution state for the analytics supervisor graph.

``WorkflowState`` subclasses LangGraph's ``MessagesState`` (so ``messages`` and
its reducer come for free) and adds the analytics fields the agent tools read
and write via ``Command`` updates (SDS §7.1). It is in-process execution state:
``query_result`` holds a ``QueryResult`` (rows as ``list[dict]``) and is
directly JSON-serializable.
"""

from typing import Optional

from langgraph.graph import MessagesState

from app.schemas.chart_config import ChartConfig
from app.schemas.sql_result import QueryResult


class WorkflowState(MessagesState):
    """Shared state for the analytics graph.

    Inherits ``messages`` (the ReAct conversation history) from ``MessagesState``.
    The SQL pipeline populates ``question``, ``generated_sql``, ``sql_explanation``,
    ``query_result``, and ``error_message``; the analysis agents populate
    ``chart_config``, ``insights``, and ``followup_questions``.

    Attributes:
        question: The user's natural-language question.
        generated_sql: The SQL produced by the SQL agent.
        sql_explanation: Plain-English explanation of the generated SQL.
        query_result: Executed query result (rows as list[dict] + metadata).
        chart_config: Typed visualization config from the VisualizationAgent.
        insights: Generated insights from the InsightAgent.
        followup_questions: Suggested follow-up questions from the FollowupAgent.
        error_message: Standard user-facing error message, if any step failed.
    """

    question: str
    generated_sql: Optional[str]
    sql_explanation: Optional[str]
    query_result: Optional[QueryResult]
    chart_config: Optional[ChartConfig]
    insights: Optional[list[str]]
    followup_questions: Optional[list[str]]
    error_message: Optional[str]
