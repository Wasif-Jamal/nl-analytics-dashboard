# Proposal: insights-generation

## Summary

Implement the **InsightAgent** (FR-9) — a `create_agent()` subagent that reads
`query_result` from `WorkflowState` and produces a list of data-grounded, plain-English
insight strings. Wire the graph with a **conditional fan-out** after the SQL Agent:
on success → parallel `[visualization_agent, insight_agent, followup_agent]` → END;
on error → END directly. Visualization and Follow-Up agents land as **stub pass-through
nodes** in this change (no logic). The Streamlit UI gains an **Insights panel** to
surface the generated insights below the results table.

---

## Why

The SQL pipeline (issue #4) delivers raw query results to `WorkflowState` but all
downstream analysis fields (`insights`, `chart_config`, `followup_questions`) remain
`None`. FR-9 requires actionable, data-grounded insights alongside every result — this
is the first of the three analysis agents to land. Implementing the graph fan-out at the
same time (with stubs for Visualization and Follow-Up) closes the architectural gap and
unblocks issues #8 and #9: they can fill in their stubs without touching graph wiring.

---

## Goals

- Implement `InsightAgent` (FR-9): agent class, `InsightTools`, `INSIGHT_SYSTEM_PROMPT`,
  `InsightOutput` Pydantic schema
- Add `VisualizationAgent` and `FollowupAgent` as stub pass-through nodes
  (placeholder prompt files included; no analysis logic)
- Rewire `AnalyticsGraph` with a conditional edge + parallel fan-out from `sql_agent`
  to all three analysis nodes
- Render insights in the Streamlit UI below the results table/metric

## Non-Goals

- Visualization Agent logic (FR-6/7) — stub only; separate issue
- Follow-Up Agent logic (FR-10) — stub only; separate issue
- Follow-up question UI rendering — separate issue
- Chart rendering — separate issue

---

## Design

### InsightAgent

Class in `app/agents/insight_agent.py`, following the exact `create_agent()` pattern
established by `SqlAgent`:

- Constructor injects `llm`, instantiates `InsightTools`, calls `create_agent()` with
  `INSIGHT_SYSTEM_PROMPT`, `state_schema=WorkflowState`, and `name="insight_agent"`.
- Exposes `self._agent` — the compiled `create_agent` graph added to the outer
  `StateGraph` as a subgraph node.
- Internal tool: `generate_insights` (defined in `InsightTools`).

### InsightTools

Class in `app/tools/insight_tools.py`. Builds one `@tool` closure in `__init__`:

**`generate_insights(tool_call_id, state)`**

- `state` injected via `Annotated[WorkflowState, InjectedState()]` — the LLM does not
  need to pass the rows as arguments; the tool reads `state["query_result"]` and
  `state["question"]` directly.
- Makes a nested `llm.with_structured_output(InsightOutput)` call, passing a
  `HumanMessage` containing the question and all rows serialized as JSON (no truncation —
  typical Superstore result sets are 10–200 rows, well within context limits).
- Returns `Command(update={"insights": result.insights, "messages": [ToolMessage(...)]})`.
- On `query_result` absent or empty rows: returns
  `Command(update={"insights": [], ...})` without calling the LLM.

### InsightOutput Schema

New file `app/schemas/insight_result.py`:

```python
class InsightOutput(BaseModel):
    insights: list[str]  # 3–5 data-grounded plain-English insight strings
```

Used only for the nested `with_structured_output` call; the outer `WorkflowState.insights`
field stays `Optional[list[str]]`.

### INSIGHT_SYSTEM_PROMPT

File `app/prompts/insight_prompt.py`. Directs the agent to call `generate_insights`
once. The nested prompt inside the tool call instructs the LLM to:

- Produce 3–5 actionable, plain-English insights
- Cite only facts supported by the returned rows (no fabricated figures)
- Focus on notable patterns: leaders/laggards, concentration, peaks, quarter-over-quarter
  changes, or anomalies visible in the data

### Stub Agents

`VisualizationAgent` (`app/agents/visualization_agent.py`) and `FollowupAgent`
(`app/agents/followup_agent.py`) each expose a `.node(state)` method that returns `{}`
(empty update — no state mutation). They are added to the outer `StateGraph` by name
as plain function nodes (not `create_agent` subgraph nodes). Placeholder prompt files
(`visualization_prompt.py`, `followup_prompt.py`) are created now so future issues can
fill them in without touching the graph.

### Graph Topology

```
sql_agent ──(error_message set)──────────────────────────────▶ END
          ──(no error)──▶ visualization_agent ──▶ END
                        ──▶ insight_agent     ──▶ END
                        ──▶ followup_agent    ──▶ END
```

Implementation in `app/orchestration/graph.py`:

```python
def _route_after_sql(state: WorkflowState) -> list[str]:
    if state.get("error_message"):
        return [END]
    return ["visualization_agent", "insight_agent", "followup_agent"]

builder.add_conditional_edges("sql_agent", _route_after_sql)
builder.add_edge("visualization_agent", END)
builder.add_edge("insight_agent", END)
builder.add_edge("followup_agent", END)
```

`AnalyticsGraph.__init__` receives the three agent instances via constructor injection
alongside the existing `llm` and `retry_limit`.

### Streamlit UI

`website/app.py` — after the results table/metric block, display the insights panel
when `insights` is non-empty:

```python
insights = data.get("insights") or []
if insights:
    st.subheader("Insights")
    for insight in insights:
        st.markdown(f"- {insight}")
```

The `future-fields-ignored` requirement in the `streamlit-ui` spec is updated:
`insights` is now rendered; `followup_questions` and `chart_config` remain parked.

---

## Files Touched

| File | Change |
|---|---|
| `app/agents/insight_agent.py` | **New** — `InsightAgent` class |
| `app/tools/insight_tools.py` | **New** — `InsightTools` with `generate_insights` |
| `app/prompts/insight_prompt.py` | **New** — `INSIGHT_SYSTEM_PROMPT` constant |
| `app/schemas/insight_result.py` | **New** — `InsightOutput` Pydantic schema |
| `app/agents/visualization_agent.py` | **New** — `VisualizationAgent` stub |
| `app/agents/followup_agent.py` | **New** — `FollowupAgent` stub |
| `app/prompts/visualization_prompt.py` | **New** — placeholder prompt module |
| `app/prompts/followup_prompt.py` | **New** — placeholder prompt module |
| `app/orchestration/graph.py` | **Update** — add three nodes + conditional fan-out |
| `website/app.py` | **Update** — add insights panel rendering |
| `tests/agents/test_insight_agent.py` | **New** — unit tests for `InsightAgent` |

---

## Open Questions

None — all design decisions resolved during spec clarification.
