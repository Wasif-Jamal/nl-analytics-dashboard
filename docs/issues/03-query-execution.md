## Requirement

Validated queries must execute against the SQL database and return their results in a structured form usable by downstream presentation, insight, and follow-up steps. Source: FRS §6.2; FR-4.

## Acceptance Criteria

1. Only queries that passed validation (issue #2) are executed.
2. A successful query returns its rows as a structured result (DataFrame).
3. Results are made available to the presentation, insight, and follow-up steps.
4. Execution is read-only and uses managed database sessions.

## Error Scenarios

| Trigger | Expected result |
|---|---|
| Database is unreachable or the query errors at runtime | `Unable to retrieve data at this time.` |
| Query executes successfully but returns zero rows | `No data found for the requested query.` |

## Out of Scope

- Validation logic (issue #2).
- Choosing/rendering the presentation of results (issue #5).
- Caching or query-performance tuning beyond the FRS §12 targets.
