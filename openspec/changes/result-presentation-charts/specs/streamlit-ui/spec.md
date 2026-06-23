# Spec Delta: streamlit-ui (result-presentation-charts)

## REMOVED Requirements

### Requirement: future-fields-ignored

The `future-fields-ignored` requirement is superseded. `chart_config` is now rendered by the UI. The four requirements below replace it.

#### Scenario: chart_config is no longer ignored
- **WHEN** the API response contains a non-None `chart_config`
- **THEN** the UI renders the appropriate presentation (metric, chart, or table) based on `chart_config["chart_type"]`

---

## ADDED Requirements

### Requirement: single-value-rendering

When the API response contains `chart_config` with `chart_type == "single_value"`, the UI SHALL render the result as `st.metric`. No chart, dataframe, CSV button, or PNG button is shown.

#### Scenario: single-value result
- **WHEN** `chart_config["chart_type"] == "single_value"`
- **THEN** `st.metric(label=chart_config["title"], value=chart_config["sentence"])` is rendered; `st.plotly_chart`, `st.dataframe`, and all download buttons are absent

---

### Requirement: chart-rendering

When the API response contains `chart_config` with `chart_type` in `{"bar", "line", "pie", "scatter"}`, the UI SHALL reconstruct a DataFrame from `query_result` and render a Plotly figure via `st.plotly_chart`.

Chart construction rules:

| chart_type | Plotly call |
|---|---|
| `bar` | `px.bar(df, x=chart_config["x"], y=chart_config["y"], title=chart_config["title"])` |
| `line` | `px.line(df, x=chart_config["x"], y=chart_config["y"], title=chart_config["title"])` |
| `pie` | `px.pie(df, names=chart_config["x"], values=chart_config["y"], title=chart_config["title"])` |
| `scatter` | `px.scatter(df, x=chart_config["x"], y=chart_config["y"], title=chart_config["title"])` |

#### Scenario: bar chart rendered
- **WHEN** `chart_config["chart_type"] == "bar"`
- **THEN** `st.plotly_chart(fig, use_container_width=True)` renders a bar chart with the correct `x`/`y` mapping and title

#### Scenario: pie chart uses names/values mapping
- **WHEN** `chart_config["chart_type"] == "pie"`
- **THEN** `px.pie` is called with `names=chart_config["x"]` and `values=chart_config["y"]`

---

### Requirement: table-fallback-rendering

When `chart_config["chart_type"] == "table"` or `chart_config` is `None` and `query_result` is non-empty, the UI SHALL render only `st.dataframe` and the CSV download button. No Plotly figure is rendered.

#### Scenario: table fallback
- **WHEN** `chart_config["chart_type"] == "table"` or `chart_config` is `None`
- **THEN** only `st.dataframe` and the CSV download button are shown; `st.plotly_chart` is absent

---

### Requirement: png-export

When a Plotly chart (`chart_type` in `{"bar", "line", "pie", "scatter"}`) is rendered, the UI SHALL display a `st.download_button` immediately below the chart that exports the figure as PNG using `plotly.io.to_image("png")`. `kaleido` must be installed as a project dependency for `to_image` to function. The PNG button SHALL be absent for `single_value` and `table` paths.

#### Scenario: PNG download button visible for chart
- **WHEN** `chart_config["chart_type"]` is one of `{"bar", "line", "pie", "scatter"}`
- **THEN** a `st.download_button` labelled "Download PNG" is rendered below the chart; clicking it downloads `chart_<YYYYMMDD_HHMMSS>.png` containing the figure as PNG

#### Scenario: PNG button absent for single_value
- **WHEN** `chart_config["chart_type"] == "single_value"`
- **THEN** no PNG download button is rendered

#### Scenario: PNG button absent for table
- **WHEN** `chart_config["chart_type"] == "table"` or `chart_config` is `None`
- **THEN** no PNG download button is rendered
