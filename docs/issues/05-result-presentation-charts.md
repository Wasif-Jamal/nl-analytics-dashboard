## Requirement

The system must present results in the clearest form for their shape: a single value becomes a plain-language sentence; multi-row results render as an appropriate chart. Charts are exportable as PNG. Source: FRS §6.3, §11; FR-6, FR-7, FR-8.

## Acceptance Criteria

1. The system selects a presentation based on result shape:
   - Single value (1×1) → plain-language sentence (e.g. "Total revenue for this quarter is 200K USD").
   - Category + measure → bar chart.
   - Time series → line chart.
   - Parts of a whole → pie chart.
   - Two numeric measures → scatter plot.
   - Other / ambiguous → table only.
2. Charts render from the returned data (Plotly).
3. Single-value results are stated as a written sentence rather than a chart.
4. Rendered visualizations can be exported as PNG.

## Error Scenarios

| Trigger | Expected result |
|---|---|
| Result shape is ambiguous or unsupported for charting | Fall back to the table-only presentation |
| Empty result set | No chart rendered; defer to the empty-state handling (issues #3/#4) |

## Out of Scope

- Generating the textual insights about the data (issue #6).
- Tabular view and CSV export (issue #4).
- Custom/user-configurable chart styling beyond automatic selection.
