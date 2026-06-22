"""Tests for app.orchestration.graph.AnalyticsGraph.

Covers the workflow-state and database-access-boundary requirements at the graph
level: the graph compiles with the WorkflowState schema and routes directly to
the ``sql_agent`` subgraph node (plain ``StateGraph``, no supervisor LLM node).
Built offline with a dummy API key (no network).
"""

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph.state import CompiledStateGraph

from app.orchestration.graph import AnalyticsGraph


def _build():
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key="test-key")
    return AnalyticsGraph(llm, retry_limit=3).build()


def test_build_returns_compiled_graph():
    """build() returns a CompiledStateGraph with exactly sql_agent as its node."""
    graph = _build()
    assert isinstance(graph, CompiledStateGraph)
    assert set(graph.nodes) == {"__start__", "sql_agent"}


def test_sql_agent_is_registered_as_subgraph():
    """The outer graph's sql_agent node wraps a compiled create_agent subgraph."""
    graph = _build()
    # graph.nodes returns PregelNode wrappers; the compiled subgraph is inside .subgraphs
    pregel_node = graph.nodes["sql_agent"]
    assert len(pregel_node.subgraphs) == 1
    assert isinstance(pregel_node.subgraphs[0], CompiledStateGraph)
