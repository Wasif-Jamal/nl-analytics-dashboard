## Requirement

Returned data must be viewable as a raw table and exportable as CSV, so users can inspect and take away the underlying records. Source: FRS §6.6, §11; FR-5, FR-12.

> Result data is available as the `query_result` field in `WorkflowState`, populated by the `query_database` tool (issue #1). The Streamlit UI reads this field from the API response to render the table.

## Acceptance Criteria

1. Query results are displayed in a tabular view of the returned records.
2. The table supports pagination and sorting.
3. The user can export the current result set as a CSV file.
4. The table reflects the exact rows returned by execution (no transformation of values).

## Error Scenarios

| Trigger | Expected result |
|---|---|
| No results to display (empty result set) | Table shows an empty state; export is disabled or yields no file |
| Export attempted with no active results | Export action disabled / no-op with an inline note |

## Out of Scope

- Chart rendering and single-value written answers (issue #5).
- PNG export of visualizations (issue #5).
- Cross-session persistence of results.
