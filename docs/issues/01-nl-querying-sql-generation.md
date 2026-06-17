## Requirement

Business users must be able to type a plain-English question and have the system translate it into a valid SQL query, with the generated SQL shown for transparency. Source: FRS §6.1, §7; FR-1, FR-2.

## Acceptance Criteria

1. The dashboard exposes a natural-language question input and an execute action; the UI submits the question via the backend API (FastAPI route → Chat Service, see issue #10).
2. Submitting a representative question (e.g. "Show monthly revenue trend for 2025", "Top 10 products by revenue") produces a corresponding SQL query.
3. The generated SQL is displayed to the user before/with results (SQL Display panel).
4. Generation targets only the known schema entities (Orders, Products, Customers, Categories, Regions).
5. The generated query is handed off to validation (issue #2) — generation never executes SQL directly.

## Error Scenarios

| Trigger | Expected result |
|---|---|
| Question references entities not in the schema ("Show dragon sales by galaxy") | `Unable to identify requested entities.` — no SQL executed |
| Empty / blank question submitted | Execute action is a no-op with an inline prompt to enter a question |

## Out of Scope

- SQL validation and read-only enforcement (issue #2).
- Query execution and result retrieval (issue #3).
- Chart/insight/follow-up generation (issues #5–#7).
