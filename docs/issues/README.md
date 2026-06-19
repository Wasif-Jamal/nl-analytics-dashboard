# GitHub Issue Drafts

High-level (epic-level) issues derived from `docs/FRS.md`. These markdown files are the source of truth for the issue bodies created on GitHub (`Wasif-Jamal/nl-analytics-dashboard`). Each issue has: a requirement linked to its FRS section, numbered acceptance criteria, error scenarios, and an out-of-scope section.

Issues #1 (SQL generation), #2 (validation), and #3 (execution) from the original node-pipeline design have been merged into a single `query_database` tool issue, reflecting the `create_agent` + `ToolNode` architecture (issue #11).

| # | Issue | FRS source | Label |
|---|---|---|---|
| 1 | [query_database Tool (NL→SQL, validation, execution)](01-query-database-tool.md) | §6.1, §6.2; FR-1, FR-2, FR-3, FR-4 | `area:sql` |
| 4 | [Results Table & CSV Export](04-results-table-csv-export.md) | §6.6, §11; FR-5, FR-12 | `area:ui` |
| 5 | [Result Presentation: Charts & Single-Value Answer](05-result-presentation-charts.md) | §6.3, §11; FR-6, FR-7, FR-8 | `area:viz` |
| 6 | [Insights Generation](06-insights-generation.md) | §6.4; FR-9 | `area:insights` |
| 7 | [Suggested Follow-Up Questions](07-suggested-followup-questions.md) | §6.5; FR-10 | `area:insights` |
| 8 | [Query History (session)](08-query-history.md) | §6.7, §7; FR-11 | `area:ui` |
| 9 | [Error Handling & Messaging](09-error-handling-messaging.md) | §10, §12 | `area:ui` |
| 10 | [API Layer (FastAPI routes & Chat Service)](10-api-layer-fastapi.md) | SDS §9.3; tech-arch §15 | `area:api` |
| 11 | [Tool-Calling Agent Architecture](11-tool-calling-agent-architecture.md) (GitHub #13) | SDS §6–8; tech-arch §5–6, §16 | `area:orchestration` |

All issues also carry the `enhancement` label.

## Recommended Build Order

| Step | Issue | Deliverable |
|---|---|---|
| 1 | #1 | `query_database` tool — SQL gen + validation + execution working end-to-end |
| 2 | #10 | FastAPI routes + Chat Service wired to `create_agent` graph |
| 3 | #11 | Full `create_agent` supervisor (all four tools + `AnalyticsGraph`) |
| 4 | #5, #6, #7 | Visualization, insights, follow-up tools (can be parallelised) |
| 5 | #4, #8, #9 | UI table/CSV export, query history panel, error display |
