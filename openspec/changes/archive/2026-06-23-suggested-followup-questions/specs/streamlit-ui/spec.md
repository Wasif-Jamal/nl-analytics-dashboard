# Spec Delta: streamlit-ui (suggested-followup-questions change)

## Delta Summary

Adds the Suggested Questions section to the Streamlit UI and narrows the
`future-fields-ignored` requirement: `followup_questions` is now rendered via the new
`followup-questions-display` requirement; only `chart_config` remains parked.

---

## ADDED Requirements

### Requirement: followup-questions-display

`website/app.py` SHALL render a **Suggested Questions** section after the insights panel
when the response contains a non-empty `followup_questions` list. Each question SHALL be
rendered as an `st.button`. Clicking a button SHALL store the question in
`st.session_state["pending_question"]` and call `st.rerun()`. On page render, if
`st.session_state["pending_question"]` is set, the question input SHALL be pre-filled
with it and the value cleared from session state (so subsequent renders do not loop).
The section SHALL be absent when `followup_questions` is `None`, an empty list, or
missing from the response. The section is only shown on the success path (inside the
`else` branch where `error_message` is `None`).

#### Scenario: follow-up questions present — section rendered
- **WHEN** `data["followup_questions"]` is a non-empty list of strings
- **THEN** `st.subheader("Suggested Questions")` is rendered, followed by one `st.button(q)` per question string; buttons use unique `key` values

#### Scenario: follow-up questions absent — no section
- **WHEN** `data["followup_questions"]` is `None`, `[]`, or absent from the response
- **THEN** no "Suggested Questions" subheader or buttons are rendered

#### Scenario: button clicked — question pre-filled and re-submitted
- **WHEN** the user clicks a suggested question button
- **THEN** `st.session_state["pending_question"]` is set to that question string and `st.rerun()` is called; on the next render the question input contains that string and `pending_question` is cleared; the normal submit flow fires and the question is processed through the full workflow

#### Scenario: error path — suggestions not shown
- **WHEN** `error_message` is set in the response
- **THEN** only the `st.warning(error_message)` is shown; the Suggested Questions section does not appear

---

## MODIFIED Requirements

### Requirement: future-fields-ignored

`chart_config` present in the response SHALL be silently ignored. `followup_questions`
is now handled by the `followup-questions-display` requirement above and SHALL NOT be
ignored. The UI reads `generated_sql`, `query_result`, `error_message`, `insights`, and
`followup_questions`.

#### Scenario: response contains chart_config
- **WHEN** the response JSON contains a non-None value for `chart_config`
- **THEN** the UI renders only the SQL panel, results table/metric, insights panel, and suggested questions section; no additional panels appear for `chart_config`

#### Scenario: followup_questions field is rendered, not ignored
- **WHEN** the response JSON contains a non-empty `followup_questions` list
- **THEN** the Suggested Questions section IS rendered (see `followup-questions-display`); it is not silently dropped
