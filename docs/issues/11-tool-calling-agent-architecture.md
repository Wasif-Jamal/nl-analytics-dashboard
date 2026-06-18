> **GitHub issue:** [#13](https://github.com/Wasif-Jamal/nl-analytics-dashboard/issues/13) (numbers 11–12 were consumed by earlier PRs).

## Requirement

Adopt a **tool-calling agent architecture** for the analytics workflow: a LangChain `create_agent` **supervisor** runs a ReAct loop over four capability **tools** exposed by the specialized agents, replacing the originally-specified hand-wired LangGraph node pipeline. This is a "how"-level change — it does not alter any functional requirement (FR-1…FR-12), the read-only rule (FRS §9), or the standard error messages (FRS §10). Source: `docs/SDS.md` §6–8, `docs/decisions/technical_architecture.md` §5–6 and the ADR in §16.

## Rationale

- `create_agent` builds the agent node, the prebuilt `ToolNode`, and routing internally — no `nodes/` package or `conditional_edges` to hand-maintain.
- SQL self-correction falls out of the ReAct loop: the `query_database` tool feeds validation/execution errors back to its own LLM and retries.
- Insight and follow-up tools *compute* their results from the returned rows (own data-grounded LLM call, read via `InjectedState`), strengthening the FR-9 anti-fabrication guarantee — they do not store supervisor-authored text.
- Visualization is deterministic (result-shape → chart-type), so it needs no LLM.

## Acceptance Criteria

1. `WorkflowState` subclasses `MessagesState` and adds `question`, `generated_sql`, `sql_explanation`, `query_result`, `chart_config`, `insights`, `followup_questions`, `error_message`.
2. Each agent (`SqlAgent`, `VisualizationAgent`, `InsightAgent`, `FollowupAgent`) exposes its capability via `get_tools()`; each tool returns a typed `Command` updating state.
3. `query_database` generates SQL, validates read-only (SELECT only), executes via the Repository, and retry-corrects on validation/execution error.
4. `AnalyticsGraph` (`app/orchestration/graph.py`) assembles the four tools and returns `create_agent(model, tools, system_prompt, state_schema=WorkflowState)`.
5. After a successful query, the supervisor emits `generate_visualization`, `generate_insights`, and `suggest_followups` in one turn; `ToolNode` runs them in parallel and their `Command` updates merge into state.
6. `ChatService` invokes the compiled graph and returns the aggregated state; in-memory session history (FR-11) is preserved.
7. Agent outputs are typed Pydantic schemas (`SQLGenerationOutput`, `ChartConfig`, `InsightOutput`, `FollowupOutput`).
8. Quality gates pass: `uv run ruff check . && uv run ruff format --check . && uv run pytest`.

## Error Scenarios

| Trigger | Expected result |
|---|---|
| Question references entities not in the schema | `query_database` sets `error_message` = `Unable to identify requested entities.`; supervisor stops without analysis tools |
| Generated SQL fails validation after retries | `Generated query could not be validated.` |
| Query executes but returns zero rows | `No data found for the requested query.` |
| Database unreachable / runtime error after retries | `Unable to retrieve data at this time.` |

## Affected / Subsumed Issues

This architecture is the implementation vehicle for and cross-cuts:

- #3 Query Execution (`query_database` tool)
- #5 Result Presentation: Charts & Single-Value Answer (`generate_visualization` tool)
- #6 Insights Generation (`generate_insights` tool)
- #7 Suggested Follow-Up Questions (`suggest_followups` tool)
- #10 API Layer (Chat Service invokes the `create_agent` graph)

## Out of Scope

- Authentication / authorization (FRS §13).
- Forecasting / predictive modeling / autonomous actions (FRS §14).
- FastAPI routes and the Streamlit UI wiring (issue #10 and the UI issues) — this issue covers the agent/graph/service layer.
- Any change to functional requirements, the read-only rule, or the standard error messages.
