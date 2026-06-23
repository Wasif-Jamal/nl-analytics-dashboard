# Spec Delta: streamlit-ui (insights-generation change)

## Delta Summary

Adds the insights panel to the Streamlit UI and narrows the `future-fields-ignored`
requirement: `insights` is now rendered via the new `insights-display` requirement;
`followup_questions` and `chart_config` remain parked for future issues.

---

## MODIFIED Requirements

### Requirement: future-fields-ignored

`followup_questions` and `chart_config` present in the response SHALL be silently
ignored. `insights` is now handled by the `insights-display` requirement and SHALL
NOT be ignored. The UI reads `generated_sql`, `query_result`, `error_message`,
and `insights`.

#### Scenario: response contains followup_questions or chart_config
- **WHEN** the response JSON contains non-None values for `followup_questions` or `chart_config`
- **THEN** the UI renders only the SQL panel, results table/metric, and insights panel; no additional panels appear for those two fields

#### Scenario: insights field is rendered, not ignored
- **WHEN** the response JSON contains a non-empty `insights` list
- **THEN** the insights panel IS rendered (see `insights-display`); it is not silently dropped

---

## ADDED Requirements

### Requirement: insights-display

`website/app.py` SHALL render an **Insights** section after the results table/metric
when the response contains a non-empty `insights` list. Each insight string SHALL be
rendered as a bullet via `st.markdown`. The section SHALL be absent when `insights`
is `None`, an empty list, or missing from the response. The insights panel is only
shown on the success path (inside the `else` branch where `error_message` is `None`).

#### Scenario: insights present — panel rendered
- **WHEN** `data["insights"]` is a non-empty list of strings
- **THEN** `st.subheader("Insights")` is rendered, followed by one `st.markdown(f"- {insight}")` call per string, in list order

#### Scenario: insights absent — no panel
- **WHEN** `data["insights"]` is `None`, `[]`, or absent from the response
- **THEN** no "Insights" subheader or markdown bullets are rendered

#### Scenario: error path — insights not shown
- **WHEN** `error_message` is set in the response
- **THEN** only the `st.warning(error_message)` is shown; the insights panel does not appear
