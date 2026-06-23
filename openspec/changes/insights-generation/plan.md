# Implementation Plan: insights-generation

Implements FR-9 (InsightAgent), stub agents for Visualization and Follow-Up,
conditional parallel fan-out in `AnalyticsGraph`, and the Streamlit insights panel.

Reference: `openspec/changes/insights-generation/proposal.md` and `spec.md`.

---

## Execution Order

Tasks are ordered by dependency. Each group can be worked independently; later
groups depend on earlier ones.

---

## Task 1 — `app/schemas/insight_result.py` (new)

**No dependencies.**

Create the `InsightOutput` Pydantic model — the structured-output target for the
nested LLM call inside `generate_insights`. Keeps the outer `WorkflowState.insights`
type (`Optional[list[str]]`) unchanged.

```python
"""Pydantic schema for InsightAgent structured output."""
from pydantic import BaseModel

class InsightOutput(BaseModel):
    """Structured LLM output from the insight generation call.

    Attributes:
        insights: 3–5 data-grounded plain-English insight strings.
    """
    insights: list[str]
```

**Pattern ref:** mirrors `SQLGenerationOutput` in `app/schemas/sql_result.py`.

---

## Task 2 — `app/prompts/insight_prompt.py` (new)

**No dependencies.**

Module-level constant only (same shape as `sql_prompt.py`). Two responsibilities:
- Outer `create_agent` system prompt: tells the agent to call `generate_insights`
  exactly once; no loop or retry needed.
- Inner nested prompt (passed in the `HumanMessage` inside the tool): instructs the
  LLM to produce 3–5 actionable, data-grounded insights; no fabricated figures.

```python
"""System prompt for InsightAgent."""

INSIGHT_SYSTEM_PROMPT = """You are a business data analyst. \
Your only task is to call generate_insights once to produce actionable insights \
from the query result that is already in state. \
Do not ask for clarification. Call the tool immediately."""

INSIGHT_INNER_PROMPT = """Analyze the following query result and produce 3–5 \
concise, actionable business insights grounded strictly in the returned data.

Rules:
- Cite only values present in the data; do not fabricate figures or trends.
- Focus on: notable leaders/laggards, concentration, peaks, significant \
  changes, or anomalies visible in the rows.
- Each insight must be a single clear sentence.

Question: {question}

Data (JSON):
{rows_json}"""
```

---

## Task 3 — `app/prompts/visualization_prompt.py` (new, placeholder)

**No dependencies.**

```python
"""Placeholder prompt for VisualizationAgent (to be implemented in issue #8)."""

VISUALIZATION_SYSTEM_PROMPT = ""
```

---

## Task 4 — `app/prompts/followup_prompt.py` (new, placeholder)

**No dependencies.**

```python
"""Placeholder prompt for FollowupAgent (to be implemented in issue #9)."""

FOLLOWUP_SYSTEM_PROMPT = ""
```

---

## Task 5 — `app/tools/insight_tools.py` (new)

**Depends on:** Tasks 1, 2.

`InsightTools` builds one `@tool` closure (`generate_insights`) in `__init__`, capturing
`llm`. Pattern mirrors `SqlTools` in `app/tools/sql_tools.py`.

### Key design: `InjectedState` for row access

`generate_insights` uses `Annotated[WorkflowState, InjectedState()]` to read
`query_result` and `question` from state. The LLM never has to pass rows as a tool
argument — it just calls `generate_insights()` with no user-supplied args.

```python
from typing import Annotated
import json
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from app.config.log_config import config as log_config
from app.orchestration.state import WorkflowState
from app.prompts.insight_prompt import INSIGHT_INNER_PROMPT
from app.schemas.insight_result import InsightOutput

logger = log_config.get_logger(__name__)

class InsightTools:
    def __init__(self, llm) -> None:

        @tool
        def generate_insights(
            tool_call_id: Annotated[str, InjectedToolCallId],
            state: Annotated[WorkflowState, InjectedState()],
        ) -> Command:
            """Generate data-grounded insights from query_result in state."""
            query_result = state.get("query_result")
            question = state.get("question", "")

            if not query_result or not query_result.rows:
                logger.info("generate_insights: no data, skipping LLM call")
                return Command(
                    update={
                        "insights": [],
                        "messages": [ToolMessage(content="No data to analyze.", tool_call_id=tool_call_id)],
                    }
                )

            rows_json = json.dumps(query_result.rows)
            prompt = INSIGHT_INNER_PROMPT.format(question=question, rows_json=rows_json)

            try:
                chain = llm.with_structured_output(InsightOutput)
                result: InsightOutput = chain.invoke([HumanMessage(content=prompt)])
                logger.info("generate_insights: produced %d insights", len(result.insights))
                summary = f"Generated {len(result.insights)} insights."
                return Command(
                    update={
                        "insights": result.insights,
                        "messages": [ToolMessage(content=summary, tool_call_id=tool_call_id)],
                    }
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("generate_insights: LLM call failed: %s", exc)
                return Command(
                    update={
                        "insights": [],
                        "messages": [ToolMessage(content="Insight generation failed.", tool_call_id=tool_call_id)],
                    }
                )

        self.generate_insights = generate_insights
```

### Exception handling note
`InsightOutput` failure is **non-fatal** — sets `insights=[]`, does NOT set
`error_message` (the SQL result is still valid and should be displayed).

---

## Task 6 — `app/agents/insight_agent.py` (new)

**Depends on:** Tasks 2, 5.

Exact pattern mirror of `SqlAgent`. No retry limit needed (single tool call).

```python
"""InsightAgent — create_agent() subagent for FR-9 data-grounded insights."""
from langchain.agents import create_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from app.config.log_config import config as log_config
from app.orchestration.state import WorkflowState
from app.prompts.insight_prompt import INSIGHT_SYSTEM_PROMPT
from app.tools.insight_tools import InsightTools

logger = log_config.get_logger(__name__)

class InsightAgent:
    """InsightAgent — create_agent() instance with generate_insights internal tool.

    self._agent is the compiled create_agent graph, added to the outer StateGraph
    as a subgraph node named "insight_agent". Its internal tool (generate_insights)
    is invisible to the outer graph.
    """

    def __init__(self, llm: ChatGoogleGenerativeAI) -> None:
        logger.info("InsightAgent initializing")
        insight_tools = InsightTools(llm=llm)
        self._agent = create_agent(
            model=llm,
            tools=[insight_tools.generate_insights],
            system_prompt=INSIGHT_SYSTEM_PROMPT,
            state_schema=WorkflowState,
            name="insight_agent",
        )
        logger.info("InsightAgent compiled")
```

---

## Task 7 — `app/agents/visualization_agent.py` (new, stub)

**Depends on:** Task 3.

```python
"""VisualizationAgent stub (to be implemented in issue #8)."""
from app.config.log_config import config as log_config
from app.orchestration.state import WorkflowState

logger = log_config.get_logger(__name__)

class VisualizationAgent:
    """Pass-through stub. node() returns {} until issue #8 implements logic."""

    def __init__(self, llm) -> None:
        logger.info("VisualizationAgent (stub) initialized")

    def node(self, state: WorkflowState) -> dict:
        """No-op stub node. Returns empty update."""
        logger.debug("VisualizationAgent stub node called")
        return {}
```

---

## Task 8 — `app/agents/followup_agent.py` (new, stub)

**Depends on:** Task 4.

```python
"""FollowupAgent stub (to be implemented in issue #9)."""
from app.config.log_config import config as log_config
from app.orchestration.state import WorkflowState

logger = log_config.get_logger(__name__)

class FollowupAgent:
    """Pass-through stub. node() returns {} until issue #9 implements logic."""

    def __init__(self, llm) -> None:
        logger.info("FollowupAgent (stub) initialized")

    def node(self, state: WorkflowState) -> dict:
        """No-op stub node. Returns empty update."""
        logger.debug("FollowupAgent stub node called")
        return {}
```

---

## Task 9 — `app/orchestration/graph.py` (update)

**Depends on:** Tasks 6, 7, 8.

Replace the current `sql_agent → END` topology with a conditional fan-out.

### Routing function (module-level, not a method)

```python
def _route_after_sql(state: WorkflowState) -> str | list[str]:
    """Route to END on error; fan-out to all three analysis nodes on success."""
    if state.get("error_message"):
        return END
    return ["visualization_agent", "insight_agent", "followup_agent"]
```

### Updated `build()` method

```python
def build(self) -> CompiledStateGraph:
    sql_agent    = SqlAgent(self._llm, retry_limit=self._retry_limit)
    viz_agent    = VisualizationAgent(self._llm)
    insight_agent  = InsightAgent(self._llm)
    followup_agent = FollowupAgent(self._llm)

    builder = StateGraph(WorkflowState)
    builder.add_node("sql_agent",          sql_agent._agent)
    builder.add_node("visualization_agent", viz_agent.node)
    builder.add_node("insight_agent",       insight_agent._agent)
    builder.add_node("followup_agent",      followup_agent.node)

    builder.set_entry_point("sql_agent")
    builder.add_conditional_edges("sql_agent", _route_after_sql)
    builder.add_edge("visualization_agent", END)
    builder.add_edge("insight_agent",       END)
    builder.add_edge("followup_agent",      END)

    graph = builder.compile()
    logger.info("Analytics graph compiled (4 nodes + conditional fan-out)")
    return graph
```

### `__init__` additions

Add imports at the top of the file:
```python
from app.agents.visualization_agent import VisualizationAgent
from app.agents.insight_agent import InsightAgent
from app.agents.followup_agent import FollowupAgent
```

The constructor signature is **unchanged** (`llm`, `retry_limit`) — the three
analysis agents are constructed inside `build()` from the same `llm`.

---

## Task 10 — `website/app.py` (update)

**No backend dependencies; can be done in parallel with Tasks 1–9.**

After the `if query_result:` block (lines 52–73), add the insights panel:

```python
# Insights panel (populated by InsightAgent)
insights = data.get("insights") or []
if insights:
    st.subheader("Insights")
    for insight in insights:
        st.markdown(f"- {insight}")
```

The panel is only visible when `error_message` is `None` (already inside the `else`
branch), so no extra guard is needed.

---

## Task 11 — `tests/agents/test_insight_agent.py` (new)

**Depends on:** Tasks 5, 6.

Mirror the structure of `tests/agents/test_sql_agent.py`:
- Call tools via `.func` attribute — bypasses LangChain wrapper, tests logic directly.
- Mock the LLM with `MagicMock`; never hit the network.
- Pass state as a plain `dict` (LangGraph accepts dict-like state in tool tests).

### Test cases

| Test | Covers spec scenario |
|---|---|
| `test_generate_insights_success` | `query_result` present → `with_structured_output` called → `insights` in `Command.update` |
| `test_generate_insights_empty_rows` | `query_result.rows == []` → no LLM call → `insights=[]` |
| `test_generate_insights_none_result` | `query_result is None` → no LLM call → `insights=[]` |
| `test_generate_insights_llm_exception` | LLM raises → `insights=[]`, `error_message` not set |
| `test_insight_agent_compiles` | `InsightAgent._agent` is a `CompiledStateGraph` |
| `test_insight_tools_passed_to_create_agent` | `InsightAgent._agent` is not `None` |

### Fixture pattern

```python
_QUERY_RESULT = QueryResult(
    rows=[{"region": "East", "sales": 1000.0}, {"region": "West", "sales": 800.0}],
    columns=["region", "sales"],
    row_count=2,
)

def _mock_state(query_result=_QUERY_RESULT, question="Show sales by region") -> dict:
    return {"query_result": query_result, "question": question, "messages": []}

def _make_tools(mock_llm=None) -> InsightTools:
    llm = mock_llm or ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key="test-key")
    return InsightTools(llm=llm)
```

### Note on calling tools with injected state

`InjectedState` params are hidden from the LLM's schema but still passed when
calling `.func` directly. Signature for `.func` call:

```python
command = tools.generate_insights.func(
    tool_call_id="tc1",
    state=_mock_state(),
)
```

---

## Task 12 — `tests/orchestration/test_graph.py` (update)

**Depends on:** Task 9.

Update `test_build_returns_compiled_graph` to expect five nodes:

```python
assert set(graph.nodes) == {
    "__start__",
    "sql_agent",
    "visualization_agent",
    "insight_agent",
    "followup_agent",
}
```

Add two new tests:

```python
def test_sql_error_routes_to_end():
    """Conditional edge returns END when error_message is set."""
    from app.orchestration.graph import _route_after_sql
    from langgraph.graph import END
    state = {"error_message": "Unable to identify requested entities.", "messages": []}
    assert _route_after_sql(state) == END

def test_sql_success_fans_out():
    """Conditional edge returns all three analysis nodes when no error."""
    from app.orchestration.graph import _route_after_sql
    state = {"error_message": None, "messages": []}
    result = _route_after_sql(state)
    assert set(result) == {"visualization_agent", "insight_agent", "followup_agent"}
```

---

## Files Summary

| File | Action | Task |
|---|---|---|
| `app/schemas/insight_result.py` | **Create** | 1 |
| `app/prompts/insight_prompt.py` | **Create** | 2 |
| `app/prompts/visualization_prompt.py` | **Create** (placeholder) | 3 |
| `app/prompts/followup_prompt.py` | **Create** (placeholder) | 4 |
| `app/tools/insight_tools.py` | **Create** | 5 |
| `app/agents/insight_agent.py` | **Create** | 6 |
| `app/agents/visualization_agent.py` | **Create** (stub) | 7 |
| `app/agents/followup_agent.py` | **Create** (stub) | 8 |
| `app/orchestration/graph.py` | **Update** — fan-out wiring | 9 |
| `website/app.py` | **Update** — insights panel | 10 |
| `tests/agents/test_insight_agent.py` | **Create** | 11 |
| `tests/orchestration/test_graph.py` | **Update** — node assertions | 12 |

No DB changes. No new env vars. No new API routes. No `AnalyticsResponse` schema
changes needed — `insights: Optional[list[str]]` already exists.

---

## Quality Gate (run in order before committing)

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

All three must be green. Fix any ruff findings before running pytest.

---

## Commit Plan

Two commits, per `feedback_commit_per_task_group.md`:

1. **`feat(insight-agent): add InsightAgent, stubs, and parallel graph fan-out`**
   Tasks 1–9, 12 — backend only; gates must pass.

2. **`feat(ui): add insights panel to Streamlit dashboard`**
   Task 10 — UI update; gates must pass.
