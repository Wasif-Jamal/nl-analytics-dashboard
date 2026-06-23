"""Unit tests for app.tools.visualization_tools.VisualizationTools and
app.agents.visualization_agent.VisualizationAgent.

Tests each of the three internal tools directly via their ``.func`` attribute
(bypassing LangChain's tool-calling wrapper), and verifies that
``VisualizationAgent`` compiles without error.

No real LLM or API key interaction is required for tool tests; only the
``test_visualization_agent_compiles`` test instantiates the agent class with a
fake API key (no network call is made during construction).

Covers spec scenarios: analyze_shape_bar, analyze_shape_single_value,
analyze_shape_table_fallback, build_chart_config_bar, build_chart_config_pie,
build_sentence, visualization_agent_compiles, visualization_prompt_not_inline.
"""

import pandas as pd
from langchain_google_genai import ChatGoogleGenerativeAI

from app.agents.visualization_agent import VisualizationAgent
from app.prompts.visualization_prompt import VISUALIZATION_SYSTEM_PROMPT
from app.schemas.chart_config import ChartConfig
from app.schemas.sql_result import QueryResult
from app.tools.visualization_tools import VisualizationTools

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_query_result(
    columns: list[str],
    data: list[list],
    row_count: int,
) -> QueryResult:
    """Build a QueryResult from raw column/data/row_count values."""
    df = pd.DataFrame(data, columns=columns)
    return QueryResult(dataframe=df, columns=columns, row_count=row_count)


def _make_tools() -> VisualizationTools:
    """Return a VisualizationTools instance."""
    return VisualizationTools()


# ---------------------------------------------------------------------------
# analyze_shape
# ---------------------------------------------------------------------------


def test_analyze_shape_bar():
    """analyze_shape returns chart_type='bar' for 1 string + 1 numeric column."""
    tools = _make_tools()
    qr = _make_query_result(
        columns=["category", "sales"],
        data=[
            ["Furniture", 10.0],
            ["Technology", 20.0],
            ["Office Supplies", 15.0],
            ["Furniture", 12.0],
            ["Technology", 18.0],
        ],
        row_count=5,
    )
    state = {"query_result": qr}
    result = tools.analyze_shape.func(state=state)

    assert result["chart_type"] == "bar"
    assert result["x"] == "category"
    assert result["y"] == "sales"


def test_analyze_shape_single_value():
    """analyze_shape returns chart_type='single_value' for 1 column, 1 row."""
    tools = _make_tools()
    qr = _make_query_result(
        columns=["total_revenue"],
        data=[[1_200_000.0]],
        row_count=1,
    )
    state = {"query_result": qr}
    result = tools.analyze_shape.func(state=state)

    assert result["chart_type"] == "single_value"
    assert result["x"] is None
    assert result["y"] is None


def test_analyze_shape_table_fallback():
    """analyze_shape returns chart_type='table' for 3+ mixed columns."""
    tools = _make_tools()
    qr = _make_query_result(
        columns=["category", "region", "sales"],
        data=[["Furniture", "East", 100.0], ["Technology", "West", 200.0]],
        row_count=2,
    )
    state = {"query_result": qr}
    result = tools.analyze_shape.func(state=state)

    assert result["chart_type"] == "table"


# ---------------------------------------------------------------------------
# build_chart_config
# ---------------------------------------------------------------------------


def test_build_chart_config_bar():
    """build_chart_config produces a Command with a bar ChartConfig."""
    tools = _make_tools()
    command = tools.build_chart_config.func(
        chart_type="bar",
        x="category",
        y="sales",
        title="Sales by Category",
        tool_call_id="tc1",
    )

    u = command.update
    assert "chart_config" in u
    config = u["chart_config"]
    assert isinstance(config, ChartConfig)
    assert config.chart_type == "bar"
    assert config.x == "category"
    assert config.y == "sales"
    assert config.title == "Sales by Category"
    assert len(u["messages"]) == 1
    assert "tc1" == u["messages"][0].tool_call_id


def test_build_chart_config_pie():
    """build_chart_config produces a Command with a pie ChartConfig."""
    tools = _make_tools()
    command = tools.build_chart_config.func(
        chart_type="pie",
        x="segment",
        y="revenue_percent",
        title="Revenue Share by Segment",
        tool_call_id="tc2",
    )

    config = command.update["chart_config"]
    assert isinstance(config, ChartConfig)
    assert config.chart_type == "pie"
    assert config.x == "segment"
    assert config.y == "revenue_percent"


# ---------------------------------------------------------------------------
# build_sentence
# ---------------------------------------------------------------------------


def test_build_sentence():
    """build_sentence produces a Command with a single_value ChartConfig."""
    tools = _make_tools()
    command = tools.build_sentence.func(
        sentence="Revenue is 1.2M",
        title="Revenue",
        tool_call_id="tc3",
    )

    u = command.update
    assert "chart_config" in u
    config = u["chart_config"]
    assert isinstance(config, ChartConfig)
    assert config.chart_type == "single_value"
    assert config.sentence == "Revenue is 1.2M"
    assert config.title == "Revenue"
    assert len(u["messages"]) == 1
    assert "tc3" == u["messages"][0].tool_call_id


# ---------------------------------------------------------------------------
# VisualizationAgent construction
# ---------------------------------------------------------------------------


def test_visualization_agent_compiles():
    """VisualizationAgent constructs _agent without error using a fake API key."""
    llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key="test-key")
    agent = VisualizationAgent(llm=llm)
    assert agent._agent is not None


# ---------------------------------------------------------------------------
# Prompt integrity
# ---------------------------------------------------------------------------


def test_visualization_prompt_not_inline():
    """VISUALIZATION_SYSTEM_PROMPT is a non-empty string constant."""
    assert isinstance(VISUALIZATION_SYSTEM_PROMPT, str)
    assert len(VISUALIZATION_SYSTEM_PROMPT) > 0
