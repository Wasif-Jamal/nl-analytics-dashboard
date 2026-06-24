"""Unit tests for app.tools.visualization_tools.VisualizationTools and
app.agents.visualization_agent.VisualizationAgent.

Tests ``select_visualization`` directly via its ``.func`` attribute (bypassing
LangChain's tool-calling wrapper), and verifies that ``VisualizationAgent``
compiles a ``create_agent`` graph.

All LLM calls (``llm.with_structured_output``) are mocked; no real API key or
network is needed.

Covers spec scenarios: multi-row result — chart type selected, single-value —
written answer produced, query_result absent — no LLM call, empty rows — no LLM
call, LLM call fails — non-fatal, rows truncated at 10, agent compiles.
"""

import json
from unittest.mock import MagicMock

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph.state import CompiledStateGraph

from app.agents.visualization_agent import VisualizationAgent
from app.schemas.chart_config import ChartConfig, ChartType
from app.schemas.sql_result import QueryResult
from app.tools.visualization_tools import VisualizationTools

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_MULTI_ROW_RESULT = QueryResult(
    rows=[{"region": "East", "sales": 1000.0}, {"region": "West", "sales": 800.0}],
    columns=["region", "sales"],
    row_count=2,
)

_SCALAR_RESULT = QueryResult(
    rows=[{"total_revenue": 2500.0}],
    columns=["total_revenue"],
    row_count=1,
)


def _mock_state(
    query_result=_MULTI_ROW_RESULT, question="Show sales by region"
) -> dict:
    """Return a minimal VisualizationAgentState-shaped dict for tool .func calls."""
    return {"query_result": query_result, "question": question, "messages": []}


def _make_tools(mock_llm=None) -> VisualizationTools:
    """Return a VisualizationTools instance with an optional mocked LLM."""
    llm = mock_llm or ChatGoogleGenerativeAI(
        model="gemini-2.0-flash", google_api_key="test-key"
    )
    return VisualizationTools(llm=llm)


# ---------------------------------------------------------------------------
# select_visualization — success path (multi-row)
# ---------------------------------------------------------------------------


def test_select_visualization_success():
    """Multi-row result: LLM called and chart_config written to Command.update."""
    expected = ChartConfig(
        chart_type=ChartType.bar,
        x_column="region",
        y_column="sales",
        title="Sales by Region",
    )
    mock_chain = MagicMock()
    mock_chain.invoke.return_value = expected
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_chain

    tools = _make_tools(mock_llm)
    command = tools.select_visualization.func(
        tool_call_id="tc1",
        state=_mock_state(),
    )

    assert command.update["chart_config"] == expected
    mock_llm.with_structured_output.assert_called_once_with(ChartConfig)
    mock_chain.invoke.assert_called_once()
    assert len(command.update["messages"]) == 1
    assert command.update["messages"][0].tool_call_id == "tc1"


# ---------------------------------------------------------------------------
# select_visualization — single-value (written answer)
# ---------------------------------------------------------------------------


def test_select_visualization_single_value():
    """1x1 result: LLM called, returns chart_type=table with written_answer."""
    expected = ChartConfig(
        chart_type=ChartType.table,
        written_answer="Total revenue is $2,500.",
    )
    mock_chain = MagicMock()
    mock_chain.invoke.return_value = expected
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_chain

    tools = _make_tools(mock_llm)
    command = tools.select_visualization.func(
        tool_call_id="tc2",
        state=_mock_state(
            query_result=_SCALAR_RESULT, question="What is total revenue?"
        ),
    )

    assert command.update["chart_config"].chart_type == ChartType.table
    assert command.update["chart_config"].written_answer == "Total revenue is $2,500."
    mock_llm.with_structured_output.assert_called_once_with(ChartConfig)


# ---------------------------------------------------------------------------
# select_visualization — empty rows
# ---------------------------------------------------------------------------


def test_select_visualization_empty_rows():
    """Empty rows: no LLM call, chart_config=None."""
    mock_llm = MagicMock()
    tools = _make_tools(mock_llm)
    empty_result = QueryResult(rows=[], columns=["region", "sales"], row_count=0)

    command = tools.select_visualization.func(
        tool_call_id="tc3",
        state=_mock_state(query_result=empty_result),
    )

    assert command.update["chart_config"] is None
    mock_llm.with_structured_output.assert_not_called()
    assert command.update["messages"][0].content == "No data."


# ---------------------------------------------------------------------------
# select_visualization — no query_result
# ---------------------------------------------------------------------------


def test_select_visualization_no_query_result():
    """query_result=None: no LLM call, chart_config=None."""
    mock_llm = MagicMock()
    tools = _make_tools(mock_llm)

    command = tools.select_visualization.func(
        tool_call_id="tc4",
        state={"query_result": None, "question": "anything", "messages": []},
    )

    assert command.update["chart_config"] is None
    mock_llm.with_structured_output.assert_not_called()


# ---------------------------------------------------------------------------
# select_visualization — LLM failure (non-fatal)
# ---------------------------------------------------------------------------


def test_select_visualization_llm_failure():
    """LLM raises: chart_config=None, error_message NOT set."""
    mock_chain = MagicMock()
    mock_chain.invoke.side_effect = RuntimeError("model unavailable")
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_chain

    tools = _make_tools(mock_llm)
    command = tools.select_visualization.func(
        tool_call_id="tc5",
        state=_mock_state(),
    )

    assert command.update["chart_config"] is None
    assert "error_message" not in command.update


# ---------------------------------------------------------------------------
# select_visualization — rows truncated at 10
# ---------------------------------------------------------------------------


def test_select_visualization_rows_truncated():
    """15 rows: only first 10 serialized in the prompt sent to the LLM."""
    mock_chain = MagicMock()
    mock_chain.invoke.return_value = ChartConfig(
        chart_type=ChartType.bar, x_column="region", y_column="sales"
    )
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_chain

    big_rows = [{"region": f"R{i}", "sales": float(i * 100)} for i in range(15)]
    big_result = QueryResult(rows=big_rows, columns=["region", "sales"], row_count=15)

    tools = _make_tools(mock_llm)
    tools.select_visualization.func(
        tool_call_id="tc6",
        state=_mock_state(query_result=big_result),
    )

    call_args = mock_chain.invoke.call_args
    prompt_text = call_args[0][0][0].content
    # Extract just the JSON line — the prompt has "\n\nChart type..." after it
    json_section = prompt_text.split("Sample data (up to 10 rows, JSON):\n")[1]
    json_str = json_section.split("\n\n")[0].strip()
    rows_in_prompt = json.loads(json_str)
    assert len(rows_in_prompt) == 10


# ---------------------------------------------------------------------------
# select_visualization — ambiguous result (table fallback, no written_answer)
# ---------------------------------------------------------------------------


def test_select_visualization_ambiguous_table_fallback():
    """Multi-row result where LLM returns chart_type=table with no written_answer."""
    expected = ChartConfig(chart_type=ChartType.table)
    mock_chain = MagicMock()
    mock_chain.invoke.return_value = expected
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_chain

    tools = _make_tools(mock_llm)
    command = tools.select_visualization.func(
        tool_call_id="tc_ambiguous",
        state=_mock_state(),
    )

    assert command.update["chart_config"].chart_type == ChartType.table
    assert command.update["chart_config"].written_answer is None
    mock_llm.with_structured_output.assert_called_once_with(ChartConfig)


# ---------------------------------------------------------------------------
# VisualizationAgent compiles
# ---------------------------------------------------------------------------


def test_visualization_agent_compiles():
    """VisualizationAgent.__init__ produces a compiled create_agent graph."""
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key="test-key")
    agent = VisualizationAgent(llm)
    assert isinstance(agent._agent, CompiledStateGraph)
