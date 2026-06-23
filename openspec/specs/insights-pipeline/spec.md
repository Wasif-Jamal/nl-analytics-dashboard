# insights-pipeline Specification

## Purpose
TBD - created by archiving change insights-generation. Update Purpose after archive.
## Requirements
### Requirement: insight-agent

`InsightAgent` in `app/agents/insight_agent.py` SHALL be a `create_agent()` instance
whose compiled agent is exposed via `self._agent` and added to the outer `StateGraph`
as a subgraph node named `"insight_agent"`. Its sole internal tool is `generate_insights`
(defined in `InsightTools`). The agent SHALL use `INSIGHT_SYSTEM_PROMPT` from
`app/prompts/insight_prompt.py` and `state_schema=WorkflowState`.

#### Scenario: supervisor routes to InsightAgent
- **WHEN** the outer graph routes to `"insight_agent"` after a successful SQL Agent run
- **THEN** `InsightAgent._agent` is invoked as a subgraph node; its internal tool `generate_insights` is invisible to the outer graph

#### Scenario: agent calls generate_insights once
- **WHEN** `InsightAgent._agent` receives state with a non-empty `query_result`
- **THEN** the LLM calls `generate_insights` exactly once; the result is written to `WorkflowState.insights` via `Command`

---

### Requirement: insight-tools

`InsightTools` in `app/tools/insight_tools.py` SHALL build one `@tool` closure
(`generate_insights`) in `__init__`, capturing `llm`. The tool SHALL be stored as
`self.generate_insights` and passed directly to `create_agent`.

`generate_insights` tool contract:
- Reads `query_result` and `question` from `WorkflowState` using
  `Annotated[WorkflowState, InjectedState()]` — the LLM does not pass rows as arguments.
- When `query_result` is set and `rows` is non-empty: makes a nested
  `llm.with_structured_output(InsightOutput)` call passing the original question and
  all rows serialized as JSON. Returns
  `Command(update={"insights": result.insights, "messages": [ToolMessage(...)]})`.
- When `query_result` is `None` or `rows` is empty: returns
  `Command(update={"insights": [], "messages": [ToolMessage(content="No data.", ...)]})` 
  without calling the LLM.
- When the LLM call raises: logs the exception, returns `Command(update={"insights": [], ...})`;
  does NOT set `error_message` (insight failure is non-fatal).

#### Scenario: query_result present — insights generated
- **WHEN** `generate_insights` is called and `state["query_result"].rows` is non-empty
- **THEN** the nested `with_structured_output(InsightOutput)` call returns an `InsightOutput` with 3–5 insight strings; `WorkflowState.insights` is set to that list and `error_message` is unchanged

#### Scenario: query_result absent — no LLM call
- **WHEN** `generate_insights` is called and `state["query_result"]` is `None`
- **THEN** `WorkflowState.insights` is set to `[]`; no LLM call is made; `error_message` is unchanged

#### Scenario: LLM call fails — non-fatal
- **WHEN** the nested `with_structured_output` call raises an exception
- **THEN** `WorkflowState.insights` is set to `[]`; the error is logged server-side; `error_message` is NOT set

---

### Requirement: insight-output-schema

`InsightOutput` in `app/schemas/insight_result.py` SHALL be a Pydantic `BaseModel`
used exclusively as the structured-output target for the nested LLM call inside
`generate_insights`. The outer `WorkflowState.insights` field type (`Optional[list[str]]`)
is unchanged.

#### Scenario: structured output validated
- **WHEN** the LLM returns a response for `with_structured_output(InsightOutput)`
- **THEN** Pydantic validates that `insights` is a `list[str]`; if validation fails, LangChain retries automatically

#### Scenario: schema is not stored in WorkflowState
- **WHEN** `generate_insights` writes to `WorkflowState`
- **THEN** it writes `result.insights` (a `list[str]`) to `WorkflowState.insights`, not the `InsightOutput` object itself

### Requirement: stub-agents

`VisualizationAgent` and `FollowupAgent` SHALL each be stub classes with a `.node(state)` method that returns an empty dict and MUST NOT mutate `WorkflowState`. Neither class SHALL call `create_agent()`. Placeholder prompt modules MUST be created at `app/prompts/visualization_prompt.py` and `app/prompts/followup_prompt.py`.

#### Scenario: stub node invoked
- **WHEN** the outer graph routes to `"visualization_agent"` or `"followup_agent"`
- **THEN** the stub's `.node()` method is called; it returns `{}`; `WorkflowState` is unchanged; the node terminates normally

#### Scenario: placeholder prompt files exist
- **WHEN** the project is checked out
- **THEN** `app/prompts/visualization_prompt.py` and `app/prompts/followup_prompt.py` exist and export a prompt constant (may be an empty string)

---

### Requirement: parallel-analysis-graph

`AnalyticsGraph` in `app/orchestration/graph.py` SHALL add a conditional edge from
`"sql_agent"` that either routes to `END` (on error) or fans out in parallel to
`["visualization_agent", "insight_agent", "followup_agent"]` (on success). All three
analysis nodes SHALL connect to `END`. No supervisor or router node is needed. The
routing function `_route_after_sql` SHALL be a module-level function.

#### Scenario: SQL Agent errors — analysis agents skipped
- **WHEN** the SQL Agent sets `error_message` in state
- **THEN** the conditional edge routes to `END`; none of the three analysis nodes are invoked

#### Scenario: SQL Agent succeeds — parallel fan-out
- **WHEN** the SQL Agent completes without setting `error_message`
- **THEN** the conditional edge routes to all three analysis nodes simultaneously; their `Command` updates merge into the shared `WorkflowState`

#### Scenario: analysis node fails — non-fatal
- **WHEN** an analysis node raises or returns `{}` without updating state
- **THEN** the remaining analysis nodes continue unaffected; `error_message` is NOT set by the graph for analysis-node failures

#### Scenario: graph compiles with five nodes
- **WHEN** `AnalyticsGraph.build()` is called
- **THEN** the compiled graph contains exactly the nodes `__start__`, `sql_agent`, `visualization_agent`, `insight_agent`, and `followup_agent`

