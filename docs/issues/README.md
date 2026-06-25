# GitHub Issue Drafts

High-level (epic-level) issues derived from `docs/FRS.md`. These markdown files are the source of truth for the issue bodies created on GitHub (`Wasif-Jamal/nl-analytics-dashboard`). Each issue has: a requirement linked to its FRS section, numbered acceptance criteria, error scenarios, and an out-of-scope section.

All issues follow the supervisor-over-subagents architecture documented in `docs/SDS.md` §6–8 and `docs/decisions/technical_architecture.md` §17. Issues #1–#4 are the foundational build ladder; issues #5–#10 extend the system with analysis, history, and error features.

| # | Issue | FRS source | Label |
|---|---|---|---|
| 1 | [SQL Pipeline (WorkflowState + AnalyticsGraph + SqlAgent)](01-sql-pipeline.md) | §6.1, §6.2; FR-1–4 | `area:sql` |
| 2 | [API Layer (FastAPI routes & Chat Service)](02-api-layer-fastapi.md) | SDS §9.3; tech-arch §15 | `area:api` |
| 3 | [Streamlit UI](03-streamlit-ui.md) | §6.1, §6.6, §11; FR-1, FR-5 | `area:ui` |
| 4 | [SQL Agent Subagent Refactor](04-sql-agent-subagent.md) | SDS §6.1; tech-arch §17 | `area:sql` |
| 5 | [Results Table & CSV Export](05-results-table-csv-export.md) | §6.6, §11; FR-5, FR-12 | `area:ui` |
| 6 | [Result Presentation: Charts & Single-Value Answer](06-result-presentation-charts.md) | §6.3, §11; FR-6, FR-7, FR-8 | `area:viz` |
| 7 | [Insights Generation](07-insights-generation.md) | §6.4; FR-9 | `area:insights` |
| 8 | [Suggested Follow-Up Questions](08-suggested-followup-questions.md) | §6.5; FR-10 | `area:insights` |
| 9 | [Conversation History (session)](09-conversation-history.md) | §6.7, §7; FR-11 | `area:ui` |
| 10 | [Error Handling & Messaging](10-error-handling-messaging.md) | §10, §12 | `area:ui` |

All issues also carry the `enhancement` label.

## Recommended Build Order

| Step | Issue | Deliverable |
|---|---|---|
| 1 | #1 | `WorkflowState` + `AnalyticsGraph` + `SqlAgent` as subagent (SQL pipeline end-to-end) |
| 2 | #2 | FastAPI routes + ChatService (backend callable over HTTP) |
| 3 | #3 | Streamlit UI (end-to-end NL→SQL→result in browser) |
| 4 | #4 | SqlAgent refactored to `create_agent()` with internal tools (`generate_sql`, `validate_sql`, `execute_sql`) |
| 5 | #6, #7, #8 | Visualization, Insight, Follow-up subagents (extend supervisor; can be parallelised) |
| 6 | #5, #9, #10 | Results table/CSV export, conversation history & chat UI, error messaging UI |
