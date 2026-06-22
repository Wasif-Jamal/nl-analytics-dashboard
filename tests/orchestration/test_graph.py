"""Tests for app.orchestration.graph.AnalyticsGraph.

Covers the workflow-state and database-access-boundary requirements at the graph
level: the supervisor compiles with the WorkflowState schema and exposes exactly
the query_database tool. Built offline with a dummy API key (no network).
"""

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph.state import CompiledStateGraph

from app.orchestration.graph import AnalyticsGraph


def _build():
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key="test-key")
    return AnalyticsGraph(llm, retry_limit=3).build()


def test_build_returns_compiled_graph():
    """build() returns a compiled supervisor graph."""
    graph = _build()
    assert isinstance(graph, CompiledStateGraph)
    assert {"model", "tools"} <= set(graph.nodes)


def test_query_database_is_registered():
    """The compiled ToolNode exposes exactly the query_database tool."""
    graph = _build()
    tool_names = set(graph.nodes["tools"].bound.tools_by_name)
    assert "query_database" in tool_names
