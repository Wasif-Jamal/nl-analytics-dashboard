## Requirement

Based on the current result, the system must suggest a few relevant follow-up questions the user can run with one click, supporting exploratory analysis. Source: FRS §6.5; FR-10.

> Implemented by the Follow-up Agent subagent — a `create_agent()` instance with its own LLM and internal tools. Operates over the original question and `query_result` from `WorkflowState`. Depends on issue #4 (agent pattern established).

## Acceptance Criteria

1. After a result is shown, the system proposes a small set of relevant follow-up questions.
2. Suggestions are derived from the current result/context (e.g. after "revenue by region," suggest "show the monthly trend for the top region").
3. Each suggestion is a one-click prompt that re-runs as a new query through the normal flow.
4. Suggestions are displayed in a dedicated Suggested Questions area.

## Error Scenarios

| Trigger | Expected result |
|---|---|
| No relevant follow-ups can be derived | Suggestions panel is hidden or empty (no filler/fabricated prompts) |
| A clicked suggestion fails downstream | Handled by the standard error flow (issue #9) for that new query |

## Out of Scope

- Automatically executing follow-ups without an explicit user click (FRS §3 — no autonomous action).
- Generating the insights themselves (issue #6).
