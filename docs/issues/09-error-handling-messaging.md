## Requirement

The system must handle failure cases gracefully and present clear, consistent, user-facing messages rather than raw errors. This is the cross-cutting spec for error messaging referenced by other issues. Source: FRS §10 (and §12 reliability); applies across FR-1…FR-12.

## Acceptance Criteria

1. Each of the four FRS §10 scenarios surfaces its exact standard message:
   - Invalid question (entities not identifiable) → `Unable to identify requested entities.`
   - Invalid / unvalidatable SQL → `Generated query could not be validated.`
   - Empty results → `No data found for the requested query.`
   - Database error → `Unable to retrieve data at this time.`
2. Errors are shown clearly in the UI; raw exceptions / stack traces are never shown to the user.
3. The app recovers gracefully — a failed query leaves the app usable for the next question (FRS §12 reliability).
4. Messages are sourced centrally so all features emit consistent wording.

## Error Scenarios

| Trigger | Expected result |
|---|---|
| Any of the four §10 conditions occurs | The corresponding standard message above is displayed |
| An unexpected/unclassified failure | A safe generic message is shown; the app stays responsive (no crash) |

## Out of Scope

- Internal logging/observability mechanics (centralized logger config) — supporting detail in CLAUDE.md/SDS, not user-facing here.
- The feature behaviors that trigger these errors (defined in issues #1–#8).
