"""Tests for app.orchestration.graph.AnalyticsGraph.

Covers the workflow-state and database-access-boundary requirements at the graph
level: the graph compiles with the WorkflowState schema and routes from
``sql_agent`` to ``visualization_agent`` on success, or to ``END`` on error
(plain ``StateGraph``, no supervisor LLM node).
Built offline with a dummy API key (no network).
"""

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END
from langgraph.graph.state import CompiledStateGraph

from app.orchestration.graph import AnalyticsGraph, route_after_sql


def _build():
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key="test-key")
    return AnalyticsGraph(llm, retry_limit=3).build()


def test_build_returns_compiled_graph():
    """build() returns a CompiledStateGraph containing sql_agent and visualization_agent."""
    graph = _build()
    assert isinstance(graph, CompiledStateGraph)
    assert "sql_agent" in graph.nodes
    assert "visualization_agent" in graph.nodes


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


# ---------------------------------------------------------------------------
# Tests — route_after_sql conditional routing
# ---------------------------------------------------------------------------


def test_route_after_sql_success():
    """route_after_sql returns 'visualization_agent' when error_message is None."""
    state = {
        "error_message": None,
        "query_result": None,
        "generated_sql": "SELECT 1",
    }
    assert route_after_sql(state) == "visualization_agent"


def test_route_after_sql_error():
    """route_after_sql returns END when error_message is set."""
    state = {"error_message": "Unable to retrieve data at this time."}
    assert route_after_sql(state) == END


def test_route_after_sql_empty_string_treated_as_falsy():
    """route_after_sql treats an empty-string error_message as no error (falsy)."""
    state = {"error_message": ""}
    assert route_after_sql(state) == "visualization_agent"


# ---------------------------------------------------------------------------
# Tests — graph node registration
# ---------------------------------------------------------------------------


def test_graph_has_visualization_node():
    """build() adds visualization_agent as a registered node in the compiled graph."""
    graph = _build()
    assert "visualization_agent" in graph.get_graph().nodes
