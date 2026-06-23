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


def test_database_access_boundary():
    """Database access is encapsulated inside the sql_agent subgraph, not the outer graph."""
    graph = _build()
    # Outer graph must have no ToolNode — no tool is directly callable at the supervisor level
    assert "tools" not in set(graph.nodes)
    # The sql_agent subgraph is the sole path to the database; it exposes its own tools node
    inner_graph = graph.nodes["sql_agent"].subgraphs[0]
    assert "tools" in set(inner_graph.nodes)
