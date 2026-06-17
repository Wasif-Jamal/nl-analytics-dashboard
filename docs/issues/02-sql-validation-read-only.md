## Requirement

Every generated query must be validated as read-only before it runs. Only `SELECT` statements are permitted; any data-modifying or schema-altering statement must be blocked. Source: FRS §6.2, §9; FR-3.

## Acceptance Criteria

1. A generated query is validated before any execution attempt.
2. `SELECT` queries pass validation.
3. The following are rejected: `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`.
4. Rejection prevents execution entirely (the query never reaches the database).
5. Validation is enforced server-side in the workflow, not only in the UI.

## Error Scenarios

| Trigger | Expected result |
|---|---|
| Generated query contains a write/DDL statement (INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE) | Query blocked, not executed → `Generated query could not be validated.` |
| Query that cannot be parsed/validated | Treated as invalid → `Generated query could not be validated.` |

## Out of Scope

- Natural-language → SQL generation (issue #1).
- Authentication / authorization (FRS §13 — out of scope for the product).
- Row-level access control.
