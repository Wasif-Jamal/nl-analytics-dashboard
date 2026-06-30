"""Conversation history schema for per-session multi-turn LLM context.

``ConversationTurn`` captures one complete question-answer exchange stored
in-memory by the Chat Service. A ``list[ConversationTurn]`` keyed by
``session_uuid`` is injected into ``WorkflowState.conversation_history``
before each graph run so all four agents receive prior-turn context (FR-11).

Only successfully answered turns are appended; errored turns are excluded from
the LLM context (per ``docs/issues/09-conversation-history.md``).
"""

from typing import Optional

from pydantic import BaseModel

from app.schemas.chart_config import ChartConfig
from app.schemas.sql_result import QueryResult


class ConversationTurn(BaseModel):
    """One question-answer exchange in the session conversation history.

    Stored in the Chat Service's in-memory ``dict[str, list[ConversationTurn]]``
    and injected into ``WorkflowState.conversation_history`` before each run.
    Agents format compact slices of these turns into their prompts; result rows
    are never sent to the LLM (keeps context bounded, per the proposal).

    Attributes:
        question: The user's natural-language question.
        generated_sql: SQL produced by the SQL agent; ``None`` on error.
        sql_explanation: Plain-English explanation of the SQL; ``None`` on error.
        query_result: Full query result; stored for completeness but excluded
            from LLM prompt formatting to bound token usage.
        chart_config: Visualization config from the VisualizationAgent.
        insights: Data-grounded insights from the InsightAgent.
        followup_questions: Suggested follow-up questions from the FollowupAgent.
            The FollowupAgent reads these from prior turns to avoid re-suggesting.
    """

    question: str
    generated_sql: Optional[str] = None
    sql_explanation: Optional[str] = None
    query_result: Optional[QueryResult] = None
    chart_config: Optional[ChartConfig] = None
    insights: Optional[list[str]] = None
    followup_questions: Optional[list[str]] = None
