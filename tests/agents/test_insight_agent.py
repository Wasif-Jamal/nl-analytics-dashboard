"""Unit tests for app.tools.insight_tools.InsightTools and app.agents.insight_agent.InsightAgent.

Tests ``generate_insights`` directly via its ``.func`` attribute (bypassing
LangChain's tool-calling wrapper), and verifies that ``InsightAgent`` compiles
a ``create_agent`` graph.

All LLM calls (``llm.with_structured_output``) are mocked; no real API key or
network is needed.

Covers spec scenarios: query_result present — insights generated,
query_result absent — no LLM call, LLM call fails — non-fatal,
agent calls generate_insights once (compilation smoke test).
"""

from unittest.mock import MagicMock

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph.state import CompiledStateGraph

from app.agents.insight_agent import InsightAgent
from app.schemas.insight_result import InsightOutput
from app.schemas.sql_result import QueryResult
from app.tools.insight_tools import InsightTools

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_QUERY_RESULT = QueryResult(
    rows=[{"region": "East", "sales": 1000.0}, {"region": "West", "sales": 800.0}],
    columns=["region", "sales"],
    row_count=2,
)


def _mock_state(query_result=_QUERY_RESULT, question="Show sales by region") -> dict:
    """Return a minimal WorkflowState-shaped dict for tool .func calls."""
    return {"query_result": query_result, "question": question, "messages": []}


def _make_tools(mock_llm=None) -> InsightTools:
    """Return an InsightTools instance, optionally with a mocked LLM."""
    llm = mock_llm or ChatGoogleGenerativeAI(
        model="gemini-2.0-flash", google_api_key="test-key"
    )
    return InsightTools(llm=llm)


# ---------------------------------------------------------------------------
# generate_insights — success path
# ---------------------------------------------------------------------------


def test_generate_insights_success():
    """generate_insights calls LLM and writes insights list to Command.update."""
    mock_chain = MagicMock()
    mock_chain.invoke.return_value = InsightOutput(
        insights=["East leads with $1000.", "West follows at $800."]
    )
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_chain

    tools = _make_tools(mock_llm)
    command = tools.generate_insights.func(
        tool_call_id="tc1",
        state=_mock_state(),
    )

    assert command.update["insights"] == [
        "East leads with $1000.",
        "West follows at $800.",
    ]
    mock_llm.with_structured_output.assert_called_once_with(InsightOutput)
    mock_chain.invoke.assert_called_once()

    messages = command.update["messages"]
    assert len(messages) == 1
    assert messages[0].tool_call_id == "tc1"


# ---------------------------------------------------------------------------
# generate_insights — empty rows
# ---------------------------------------------------------------------------


def test_generate_insights_empty_rows():
    """generate_insights skips LLM call and returns insights=[] when rows is empty."""
    mock_llm = MagicMock()
    tools = _make_tools(mock_llm)
    empty_result = QueryResult(rows=[], columns=["region", "sales"], row_count=0)

    command = tools.generate_insights.func(
        tool_call_id="tc2",
        state=_mock_state(query_result=empty_result),
    )

    assert command.update["insights"] == []
    mock_llm.with_structured_output.assert_not_called()


# ---------------------------------------------------------------------------
# generate_insights — None query_result
# ---------------------------------------------------------------------------


def test_generate_insights_none_result():
    """generate_insights skips LLM call and returns insights=[] when query_result is None."""
    mock_llm = MagicMock()
    tools = _make_tools(mock_llm)

    command = tools.generate_insights.func(
        tool_call_id="tc3",
        state=_mock_state(query_result=None),
    )

    assert command.update["insights"] == []
    mock_llm.with_structured_output.assert_not_called()


# ---------------------------------------------------------------------------
# generate_insights — LLM exception (non-fatal)
# ---------------------------------------------------------------------------


def test_generate_insights_llm_exception():
    """LLM failure sets insights=[] and does NOT set error_message."""
    mock_chain = MagicMock()
    mock_chain.invoke.side_effect = RuntimeError("LLM unavailable")
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_chain

    tools = _make_tools(mock_llm)
    command = tools.generate_insights.func(
        tool_call_id="tc4",
        state=_mock_state(),
    )

    assert command.update["insights"] == []
    assert command.update.get("error_message") is None


# ---------------------------------------------------------------------------
# InsightAgent — compilation and node
# ---------------------------------------------------------------------------


def test_insight_agent_compiles():
    """InsightAgent._agent is a CompiledStateGraph with InsightAgentState."""
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key="test-key")
    agent = InsightAgent(llm)
    assert isinstance(agent._agent, CompiledStateGraph)


def test_insight_agent_node_invokes_agent_with_fresh_state():
    """node() calls _agent.invoke with fresh messages and returns only insights."""
    from unittest.mock import patch

    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key="test-key")
    agent = InsightAgent(llm)

    mock_result = {
        "messages": [],
        "insights": ["East leads sales.", "Margin dipped in Q3."],
        "question": "Show sales by region",
        "query_result": None,
    }
    outer_state = {
        "question": "Show sales by region",
        "query_result": _QUERY_RESULT,
        "messages": [],
    }

    with patch.object(agent._agent, "invoke", return_value=mock_result) as mock_invoke:
        result = agent.node(outer_state)

    assert result == {"insights": ["East leads sales.", "Margin dipped in Q3."]}
    call_input = mock_invoke.call_args[0][0]
    # Fresh context: exactly one HumanMessage, not the outer SQL history
    assert len(call_input["messages"]) == 1
    assert call_input["question"] == "Show sales by region"
    assert call_input["query_result"] is _QUERY_RESULT


def test_insight_tools_attribute_set():
    """InsightTools exposes generate_insights as an instance attribute."""
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key="test-key")
    tools = InsightTools(llm=llm)
    assert tools.generate_insights is not None
