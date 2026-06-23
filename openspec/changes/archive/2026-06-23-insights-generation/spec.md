# Spec: insights-generation (delta)

## Purpose

Defines the **InsightAgent** (FR-9), its `InsightTools`, the `InsightOutput` schema,
stub agents for Visualization and Follow-Up, the conditional parallel fan-out in
`AnalyticsGraph`, and the Streamlit insights panel. This delta also patches the
`streamlit-ui` spec: `future-fields-ignored` is narrowed to `followup_questions`
and `chart_config` only; `insights` is now rendered via `insights-display`.

---

## Requirements

### Requirement: insight-agent

`InsightAgent` in `app/agents/insight_agent.py` SHALL be a `create_agent()` instance
whose compiled agent is exposed via `self._agent` and added to the outer `StateGraph`
as a subgraph node named `"insight_agent"`. Its sole internal tool is `generate_insights`
(defined in `InsightTools`). The agent SHALL use `INSIGHT_SYSTEM_PROMPT` from
`app/prompts/insight_prompt.py` and `state_schema=WorkflowState`.

#### Scenario: supervisor routes to InsightAgent
- **WHEN** the outer graph routes to `"insight_agent"` after a successful SQL Agent run
- **THEN** `InsightAgent._agent` is invoked as a subgraph node; its internal tool
  `generate_insights` is invisible to the outer graph

#### Scenario: agent calls generate_insights once
- **WHEN** `InsightAgent._agent` receives state with a non-empty `query_result`
- **THEN** the LLM calls `generate_insights` exactly once; the result is written
  to `WorkflowState.insights` via `Command`

---

### Requirement: insight-tools

`InsightTools` in `app/tools/insight_tools.py` SHALL build one `@tool` closure
(`generate_insights`) in `__init__`, capturing `llm`. The tool SHALL be stored as
`self.generate_insights` and passed directly to `create_agent`.

**`generate_insights` tool contract:**

- Reads `query_result` and `question` from `WorkflowState` using
  `Annotated[WorkflowState, InjectedState()]` — the LLM does not pass rows as arguments.
- When `query_result` is set and `rows` is non-empty: makes a nested
  `llm.with_structured_output(InsightOutput)` call passing the original question and
  all rows serialized as JSON. Returns
  `Command(update={"insights": result.insights, "messages": [ToolMessage(...)]})`.
- When `query_result` is `None` or `rows` is empty: returns
  `Command(update={"insights": [], "messages": [ToolMessage(content="No data.", ...)]})` 
  without calling the LLM.

#### Scenario: query_result present — insights generated
- **WHEN** `generate_insights` is called and `state["query_result"].rows` is non-empty
- **THEN** the nested `with_structured_output(InsightOutput)` call returns an
  `InsightOutput` with 3–5 insight strings; `WorkflowState.insights` is set to that
  list and `error_message` is unchanged

#### Scenario: query_result absent — no LLM call
- **WHEN** `generate_insights` is called and `state["query_result"]` is `None`
- **THEN** `WorkflowState.insights` is set to `[]`; no LLM call is made;
  `error_message` is unchanged

#### Scenario: LLM call fails
- **WHEN** the nested `with_structured_output` call raises an exception
- **THEN** `WorkflowState.insights` is set to `[]`; the error is logged server-side;
  `error_message` is NOT set (insight failure is non-fatal — the SQL result is still valid)

---

### Requirement: insight-output-schema

`InsightOutput` in `app/schemas/insight_result.py` SHALL be a Pydantic `BaseModel`
used exclusively as the structured-output target for the nested LLM call inside
`generate_insights`.

```
InsightOutput
  insights: list[str]   # 3–5 data-grounded plain-English insight strings
```

The outer `WorkflowState.insights` field type (`Optional[list[str]]`) is unchanged.

#### Scenario: structured output validated
- **WHEN** the LLM returns a response for `with_structured_output(InsightOutput)`
- **THEN** Pydantic validates that `insights` is a `list[str]`; if validation fails,
  LangChain retries automatically (built-in `with_structured_output` behaviour)

---

### Requirement: stub-agents

`VisualizationAgent` in `app/agents/visualization_agent.py` and `FollowupAgent` in
`app/agents/followup_agent.py` SHALL each be a class exposing a `.node(state)` method
that returns `{}` (empty dict — no state mutation). They SHALL NOT use `create_agent()`.
Placeholder prompt modules SHALL exist at `app/prompts/visualization_prompt.py` and
`app/prompts/followup_prompt.py` so future issues can fill in logic without touching
the graph wiring.

#### Scenario: stub node invoked
- **WHEN** the outer graph routes to `"visualization_agent"` or `"followup_agent"`
- **THEN** the stub's `.node()` method is called; it returns `{}`; `WorkflowState`
  is unchanged; the node terminates normally

---

### Requirement: parallel-analysis-graph

`AnalyticsGraph` in `app/orchestration/graph.py` SHALL add a conditional edge from
`"sql_agent"` that either routes to `END` (on error) or fans out in parallel to
`["visualization_agent", "insight_agent", "followup_agent"]` (on success). All three
analysis nodes SHALL connect to `END`. No supervisor/router node is needed.

```
sql_agent ──(error_message set)──▶ END
          ──(no error)──▶ visualization_agent ──▶ END
                        ──▶ insight_agent     ──▶ END
                        ──▶ followup_agent    ──▶ END
```

The routing function `_route_after_sql(state: WorkflowState) -> list[str]`:
- Returns `[END]` when `state.get("error_message")` is truthy.
- Returns `["visualization_agent", "insight_agent", "followup_agent"]` otherwise.

`AnalyticsGraph.__init__` SHALL accept `llm`, `retry_limit`, and the three analysis
agent instances (or construct them internally from `llm`).

#### Scenario: SQL Agent errors — analysis agents skipped
- **WHEN** the SQL Agent sets `error_message` in state
- **THEN** the conditional edge routes to `END`; none of the three analysis nodes
  are invoked

#### Scenario: SQL Agent succeeds — parallel fan-out
- **WHEN** the SQL Agent completes without setting `error_message`
- **THEN** the conditional edge routes to all three analysis nodes simultaneously;
  their `Command` updates merge into the shared `WorkflowState`

#### Scenario: analysis node fails — error is non-fatal
- **WHEN** an analysis node (visualization, insight, or followup stub) raises or returns
  `{}` without updating state
- **THEN** the remaining analysis nodes continue unaffected; the final state reflects
  whatever updates the other nodes produced; `error_message` is NOT set by the graph
  itself for analysis-node failures

---

### Requirement: insights-display

`website/app.py` SHALL render an **Insights** section after the results table/metric
when the response contains a non-empty `insights` list. Each insight string SHALL be
rendered as a bullet via `st.markdown`. The section SHALL be absent when `insights`
is `None`, an empty list, or missing from the response.

#### Scenario: insights present — panel rendered
- **WHEN** `data["insights"]` is a non-empty list of strings
- **THEN** `st.subheader("Insights")` is rendered, followed by one
  `st.markdown(f"- {insight}")` call per string, in list order

#### Scenario: insights absent — no panel
- **WHEN** `data["insights"]` is `None`, `[]`, or absent
- **THEN** no "Insights" subheader or markdown bullets are rendered

---

### Requirement: future-fields-ignored (updated)

`followup_questions` and `chart_config` present in the response SHALL be silently
ignored. `insights` is now handled by `insights-display` above and SHALL NOT be
ignored. The UI reads `generated_sql`, `query_result`, `error_message`, and `insights`.

#### Scenario: response contains followup_questions or chart_config
- **WHEN** the response JSON contains non-None values for `followup_questions`
  or `chart_config`
- **THEN** the UI renders only the SQL panel, results table/metric, and insights panel;
  no additional panels appear for those two fields
