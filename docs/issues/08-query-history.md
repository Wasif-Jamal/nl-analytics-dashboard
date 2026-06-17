## Requirement

The system must keep a session-level history of the questions a user has asked, and let them view and re-run previous questions. Source: FRS §6.7, §7; FR-11.

## Acceptance Criteria

1. Each executed question is recorded in a session-scoped history.
2. The user can view previously executed questions in a Query History panel.
3. Selecting a history entry re-runs that question through the normal flow.
4. History reflects the order of execution within the active session.

## Error Scenarios

| Trigger | Expected result |
|---|---|
| No questions have been run yet | History panel shows an empty state |
| A re-run history entry fails downstream | Handled by the standard error flow (issue #9) |

## Out of Scope

- Cross-session / persistent history beyond the active session (FRS §13–14).
- Sharing history or dashboards with other users (FRS §14).
