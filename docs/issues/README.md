# GitHub Issue Drafts

High-level (epic-level) issues derived from `docs/FRS.md`. These markdown files are the source of truth for the issue bodies created on GitHub (`Wasif-Jamal/nl-analytics-dashboard`). Each issue has: a requirement linked to its FRS section, numbered acceptance criteria, error scenarios, and an out-of-scope section.

All issues follow the `create_agent` + `ToolNode` architecture documented in `docs/SDS.md` §6–8 and `docs/decisions/technical_architecture.md` §16. Issues #1–#3 are the foundational build ladder; issues #4–#9 extend the pipeline with analysis, history, and error features.

| # | Issue | FRS source | Label |
|---|---|---|---|
| 1 | [query_database Tool (WorkflowState + AnalyticsGraph + SqlAgent)](01-query-database-tool.md) | §6.1, §6.2; FR-1–4 | `area:sql` |
| 2 | [API Layer (FastAPI routes & Chat Service)](02-api-layer-fastapi.md) | SDS §9.3; tech-arch §15 | `area:api` |
| 3 | [Streamlit UI](03-streamlit-ui.md) | §6.1, §6.6, §11; FR-1, FR-5 | `area:ui` |
| 4 | [Results Table & CSV Export](04-results-table-csv-export.md) | §6.6, §11; FR-5, FR-12 | `area:ui` |
| 5 | [Result Presentation: Charts & Single-Value Answer](05-result-presentation-charts.md) | §6.3, §11; FR-6, FR-7, FR-8 | `area:viz` |
| 6 | [Insights Generation](06-insights-generation.md) | §6.4; FR-9 | `area:insights` |
| 7 | [Suggested Follow-Up Questions](07-suggested-followup-questions.md) | §6.5; FR-10 | `area:insights` |
| 8 | [Query History (session)](08-query-history.md) | §6.7, §7; FR-11 | `area:ui` |
| 9 | [Error Handling & Messaging](09-error-handling-messaging.md) | §10, §12 | `area:ui` |

All issues also carry the `enhancement` label.

## Recommended Build Order

| Step | Issue | Deliverable |
|---|---|---|
| 1 | #1 | `WorkflowState` + `AnalyticsGraph` + `SqlAgent` + `query_database` tool (SQL pipeline end-to-end) |
| 2 | #2 | FastAPI routes + ChatService (backend callable over HTTP) |
| 3 | #3 | Streamlit UI (end-to-end NL→SQL→result in browser) |
| 4 | #5, #6, #7 | Visualization, insights, follow-up tools (extend graph; can be parallelised) |
| 5 | #4, #8, #9 | Results table/CSV export, query history panel, error messaging UI |
