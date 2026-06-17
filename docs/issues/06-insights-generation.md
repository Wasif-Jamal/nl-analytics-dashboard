## Requirement

Alongside the chart or written answer, the system must generate a short set of actionable insights derived strictly from the returned data — never fabricated. Source: FRS §6.4; FR-9.

## Acceptance Criteria

1. After a successful query, the system produces a concise set of plain-language insights.
2. Insights highlight notable patterns grounded in the actual values returned — e.g. peaks, leaders/laggards, concentration, quarter-over-quarter change.
3. Every figure or claim in an insight traces to the returned data; no numbers or conclusions are introduced that the data does not support.
4. Insights are shown in a dedicated insights panel next to the result.

## Error Scenarios

| Trigger | Expected result |
|---|---|
| Result set is empty or too small to support any insight | No insights are shown (rather than fabricating any) |
| Data does not support a meaningful pattern | Insights panel stays empty / states that nothing notable was found |

## Out of Scope

- Forecasting, predictive or statistical modeling (FRS §14).
- Suggested follow-up questions (issue #7).
- Recommendations that take action on the user's behalf (FRS §3).
