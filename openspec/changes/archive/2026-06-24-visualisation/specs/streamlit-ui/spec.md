# Spec Delta: streamlit-ui (visualisation change)

## Delta Summary

Adds chart rendering to the Streamlit UI and retires `chart_config` from
`future-fields-ignored`: `chart_config` is now rendered via the new `chart-display`
requirement. The `future-fields-ignored` requirement is narrowed accordingly.

---

## MODIFIED Requirements

### Requirement: future-fields-ignored

`chart_config` is now handled by `chart-display` below and SHALL NOT be silently
ignored. The UI reads `generated_sql`, `query_result`, `error_message`, `insights`,
`followup_questions`, and `chart_config`.

#### Scenario: all active response fields are rendered
- **WHEN** the response JSON contains non-None values for `chart_config`, `insights`,
  and `followup_questions`
- **THEN** all three are rendered by their respective requirements (`chart-display`,
  `insights-display`, `followup-questions-display`); no field is silently dropped

#### Scenario: response contains only chart_config
- **WHEN** the response JSON contains a non-None `chart_config` and no other analytics fields
- **THEN** the chart-display requirement governs rendering; `chart_config` is not ignored

---

## ADDED Requirements

### Requirement: chart-display

`website/app.py` SHALL render a **Visualization** section after the SQL display panel
when the response contains a non-None `chart_config`. The rendering path depends on
`chart_config["chart_type"]` and `chart_config["written_answer"]`:

1. **Written-answer path** (`written_answer` is set): render `st.info(written_answer)`.
   No chart figure, no PNG button, no dataframe, no CSV download button. The existing
   `st.metric` single-value path is removed and replaced by this path.
2. **Chart path** (`chart_type` in `{bar, line, pie, scatter}`): call
   `chart_helpers.build_figure(chart_config, query_result)`. If figure is non-None:
   render `st.plotly_chart(fig, use_container_width=True)` and a **Download PNG**
   `st.download_button` below it. If `build_figure` returns `None`: fall through to
   the dataframe path.
3. **Table-only path** (`chart_type == "table"` and no `written_answer`): no chart
   rendered; the existing `st.dataframe` + CSV download button are shown as normal.
4. **Fallback** (`chart_config` is `None`): existing behavior — `st.dataframe` + CSV
   download button.

#### Scenario: written answer rendered
- **WHEN** `chart_config["written_answer"]` is a non-empty string
- **THEN** `st.info(chart_config["written_answer"])` is rendered; no `st.metric`,
  no chart figure, no PNG download button, no dataframe, and no CSV download button
  are shown

#### Scenario: chart rendered with PNG download
- **WHEN** `chart_config["chart_type"]` is one of `{bar, line, pie, scatter}` and
  `build_figure` returns a non-None figure
- **THEN** `st.plotly_chart(fig, use_container_width=True)` is rendered; a
  `st.download_button` labelled "Download PNG" is rendered below it; the download
  triggers `fig.to_image(format="png")` with filename `chart_<YYYYMMDD_HHMMSS>.png`

#### Scenario: table-only path — ambiguous result
- **WHEN** `chart_config["chart_type"] == "table"` and `chart_config["written_answer"]`
  is None
- **THEN** no chart figure is rendered; the existing `st.dataframe` and CSV download
  button are shown

#### Scenario: chart_config absent — existing behavior unchanged
- **WHEN** `chart_config` is `None` or absent from the response
- **THEN** the existing `st.dataframe` + CSV download button path is followed unchanged
