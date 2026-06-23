# Spec Delta: streamlit-ui (results-table-csv-export change)

## Delta Summary

Enhances the results table to support native sorting and virtual scroll via a fixed-height `st.dataframe`, and adds a CSV download button that exports the full result set with a timestamped filename. All existing requirements are unchanged except `results-display`, which is updated. `csv-export` is new.

---

## MODIFIED Requirements

### Requirement: results-display

If the response contains a non-None, non-empty `query_result`, the UI SHALL display the rows in a fixed-height `st.dataframe` with virtual scrolling and native column-header sorting enabled.

#### Scenario: rows present in response
- **WHEN** `query_result` is a non-empty list of dicts in the response
- **THEN** `st.dataframe(query_result, width="stretch", height=400)` is rendered below the SQL panel, providing virtual scroll for large result sets and click-to-sort on column headers

#### Scenario: empty result set
- **WHEN** `query_result` is `None`, an empty list, or absent
- **THEN** no dataframe is rendered (the backend will have set `error_message`, which `error-display` surfaces)

---

## ADDED Requirements

### Requirement: csv-export

When `query_result` is non-empty, the UI SHALL render a `st.download_button` immediately below the results table that exports the full result set as a CSV file. The button SHALL be absent when no results are available.

#### Scenario: results present — download button visible
- **WHEN** `query_result` is a non-empty list of dicts
- **THEN** a `st.download_button` labelled "Download CSV" is rendered below the dataframe; clicking it downloads a file named `query_results_<YYYYMMDD_HHMMSS>.csv` (timestamp formatted at render time) containing all rows, with column headers, as UTF-8 CSV; `index` is not included in the CSV output

#### Scenario: results present — CSV content is exact
- **WHEN** the user clicks "Download CSV"
- **THEN** the downloaded bytes equal `pd.DataFrame(query_result).to_csv(index=False).encode("utf-8")`; no values are transformed or omitted

#### Scenario: no results — download button absent
- **WHEN** `query_result` is `None` or an empty list
- **THEN** no download button is rendered; the `error-display` requirement handles messaging
