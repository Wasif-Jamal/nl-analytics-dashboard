"""Unit tests for app.tools.followup_tools.FollowupTools and app.agents.followup_agent.FollowupAgent.

Tests ``generate_followup_questions`` directly via its ``.func`` attribute (bypassing
LangChain's tool-calling wrapper), and verifies that ``FollowupAgent`` compiles
a ``create_agent`` graph.

All LLM calls (``llm.with_structured_output``) are mocked; no real API key or
network is needed.

Covers spec scenarios: query_result present — questions generated,
query_result absent — no LLM call, LLM call fails — non-fatal,
agent calls generate_followup_questions once (compilation smoke test).
"""

from unittest.mock import MagicMock

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph.state import CompiledStateGraph

from app.agents.followup_agent import FollowupAgent
from app.schemas.followup_result import FollowupOutput
from app.schemas.sql_result import QueryResult
from app.tools.followup_tools import FollowupTools

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


def _make_tools(mock_llm=None) -> FollowupTools:
    """Return a FollowupTools instance, optionally with a mocked LLM."""
    llm = mock_llm or ChatGoogleGenerativeAI(
        model="gemini-2.0-flash", google_api_key="test-key"
    )
    return FollowupTools(llm=llm)


# ---------------------------------------------------------------------------
# generate_followup_questions — success path
# ---------------------------------------------------------------------------


def test_generate_followup_questions_success():
    """generate_followup_questions calls LLM and writes questions list to Command.update."""
    mock_chain = MagicMock()
    mock_chain.invoke.return_value = FollowupOutput(
        followup_questions=[
            "Which sub-category drives the most revenue in the East?",
            "How does West region profit compare to East?",
            "What are the top products by sales in the East?",
        ]
    )
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_chain

    tools = _make_tools(mock_llm)
    command = tools.generate_followup_questions.func(
        tool_call_id="tc1",
        state=_mock_state(),
    )

    assert command.update["followup_questions"] == [
        "Which sub-category drives the most revenue in the East?",
        "How does West region profit compare to East?",
        "What are the top products by sales in the East?",
    ]
    mock_llm.with_structured_output.assert_called_once_with(FollowupOutput)
    mock_chain.invoke.assert_called_once()

    messages = command.update["messages"]
    assert len(messages) == 1
    assert messages[0].tool_call_id == "tc1"


# ---------------------------------------------------------------------------
# generate_followup_questions — empty rows
# ---------------------------------------------------------------------------


def test_generate_followup_questions_empty_rows():
    """generate_followup_questions skips LLM call and returns [] when rows is empty."""
    mock_llm = MagicMock()
    tools = _make_tools(mock_llm)
    empty_result = QueryResult(rows=[], columns=["region", "sales"], row_count=0)

    command = tools.generate_followup_questions.func(
        tool_call_id="tc2",
        state=_mock_state(query_result=empty_result),
    )

    assert command.update["followup_questions"] == []
    mock_llm.with_structured_output.assert_not_called()


# ---------------------------------------------------------------------------
# generate_followup_questions — None query_result
# ---------------------------------------------------------------------------


def test_generate_followup_questions_none_result():
    """generate_followup_questions skips LLM call and returns [] when query_result is None."""
    mock_llm = MagicMock()
    tools = _make_tools(mock_llm)

    command = tools.generate_followup_questions.func(
        tool_call_id="tc3",
        state=_mock_state(query_result=None),
    )

    assert command.update["followup_questions"] == []
    mock_llm.with_structured_output.assert_not_called()


# ---------------------------------------------------------------------------
# generate_followup_questions — LLM exception (non-fatal)
# ---------------------------------------------------------------------------


def test_generate_followup_questions_llm_exception():
    """LLM failure sets followup_questions=[] and does NOT set error_message."""
    mock_chain = MagicMock()
    mock_chain.invoke.side_effect = RuntimeError("LLM unavailable")
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_chain

    tools = _make_tools(mock_llm)
    command = tools.generate_followup_questions.func(
        tool_call_id="tc4",
        state=_mock_state(),
    )

    assert command.update["followup_questions"] == []
    assert command.update.get("error_message") is None


# ---------------------------------------------------------------------------
# FollowupAgent — compilation and node
# ---------------------------------------------------------------------------


def test_followup_agent_compiles():
    """FollowupAgent._agent is a CompiledStateGraph with FollowupAgentState."""
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key="test-key")
    agent = FollowupAgent(llm)
    assert isinstance(agent._agent, CompiledStateGraph)


def test_followup_agent_node_invokes_agent_with_fresh_state():
    """node() calls _agent.invoke with fresh messages and returns only followup_questions."""
    from unittest.mock import patch

    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key="test-key")
    agent = FollowupAgent(llm)

    mock_result = {
        "messages": [],
        "followup_questions": [
            "Which sub-category leads in the East?",
            "How does Q4 compare to Q3?",
        ],
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

    assert result == {
        "followup_questions": [
            "Which sub-category leads in the East?",
            "How does Q4 compare to Q3?",
        ]
    }
    call_input = mock_invoke.call_args[0][0]
    # Fresh context: exactly one HumanMessage, not the outer SQL history
    assert len(call_input["messages"]) == 1
    assert call_input["question"] == "Show sales by region"
    assert call_input["query_result"] is _QUERY_RESULT


def test_generate_followup_questions_row_truncation():
    """Only 50 rows are serialized to the prompt when result set is larger."""
    import json

    mock_chain = MagicMock()
    mock_chain.invoke.return_value = FollowupOutput(
        followup_questions=["q1", "q2", "q3"]
    )
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_chain

    tools = _make_tools(mock_llm)
    big_result = QueryResult(
        rows=[{"region": "East", "sales": float(i)} for i in range(60)],
        columns=["region", "sales"],
        row_count=60,
    )
    tools.generate_followup_questions.func(
        tool_call_id="tc-trunc",
        state={"query_result": big_result, "question": "test", "messages": []},
    )

    call_args = mock_chain.invoke.call_args[0][0]
    prompt_text = call_args[0].content
    after_header = prompt_text.split("Data returned (JSON rows):\n")[1]
    # rows JSON ends at the first blank line (history sections follow)
    rows_json_part = after_header.split("\n\n")[0].strip()
    rows_sent = json.loads(rows_json_part)
    assert len(rows_sent) == 50


def test_followup_agent_node_returns_only_followup_questions():
    """node() result dict contains ONLY followup_questions — no messages, question, or query_result."""
    from unittest.mock import patch

    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key="test-key")
    agent = FollowupAgent(llm)

    mock_result = {
        "messages": [],
        "followup_questions": ["q1", "q2"],
        "question": "Show sales by region",
        "query_result": None,
    }
    outer_state = {
        "question": "Show sales by region",
        "query_result": _QUERY_RESULT,
        "messages": [],
    }

    with patch.object(agent._agent, "invoke", return_value=mock_result):
        result = agent.node(outer_state)

    assert set(result.keys()) == {"followup_questions"}


def test_followup_tools_attribute_set():
    """FollowupTools exposes generate_followup_questions as an instance attribute."""
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key="test-key")
    tools = FollowupTools(llm=llm)
    assert tools.generate_followup_questions is not None
