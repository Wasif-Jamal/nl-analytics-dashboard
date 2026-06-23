# streamlit-ui Specification

## Purpose
TBD - created by archiving change streamlit-ui. Update Purpose after archive.
## Requirements
### Requirement: session-initialisation
On first load, a `session_uuid` (UUID4) SHALL be generated and stored in `st.session_state`. The same UUID SHALL be sent with every subsequent request within the session.

#### Scenario: first page load
- **WHEN** a user opens the app for the first time
- **THEN** `st.session_state` contains a `session_uuid` key whose value is a valid UUID4 string

#### Scenario: subsequent interactions
- **WHEN** the user submits one or more questions after the initial load
- **THEN** the same `session_uuid` is included in every `POST /api/chat` request body; it is never regenerated mid-session

---

### Requirement: question-submission
The UI SHALL present a text input and a submit button on the main page. On submit, it SHALL POST `{"session_uuid": <uuid>, "question": <text>}` to `http://localhost:8000/api/chat`.

#### Scenario: valid question submitted
- **WHEN** the user types a non-empty question and clicks submit
- **THEN** the app POSTs `{"session_uuid": <uuid>, "question": <text>}` to `http://localhost:8000/api/chat` with `Content-Type: application/json`

#### Scenario: empty question submitted
- **WHEN** the user clicks submit with an empty or whitespace-only input
- **THEN** no HTTP request is made; an inline prompt ("Please enter a question") is shown; the page state is otherwise unchanged

---

### Requirement: loading-state
While the HTTP request is in flight, the UI SHALL display a loading spinner. The spinner SHALL be dismissed as soon as the response arrives, regardless of success or failure.

#### Scenario: request in flight
- **WHEN** a valid question has been submitted and the response has not yet arrived
- **THEN** a `st.spinner` is visible; the submit button is not re-entrant during this period

#### Scenario: request completes
- **WHEN** the response arrives (success or error)
- **THEN** the spinner is dismissed and results or error messaging is rendered

---

### Requirement: sql-display
If the response contains a non-None `generated_sql`, the UI SHALL display it in a collapsible panel with SQL syntax highlighting.

#### Scenario: SQL present in response
- **WHEN** `generated_sql` is a non-empty string in the response
- **THEN** an `st.expander` labelled "Generated SQL" is rendered; inside it, `st.code(generated_sql, language="sql")` displays the query

#### Scenario: SQL absent in response
- **WHEN** `generated_sql` is `None` or absent
- **THEN** no SQL panel is rendered

---

### Requirement: results-display

If the response contains a non-None, non-empty `query_result`, the UI SHALL display the rows in a fixed-height `st.dataframe` with virtual scrolling and native column-header sorting enabled.

#### Scenario: rows present in response
- **WHEN** `query_result` is a non-empty list of dicts in the response
- **THEN** `st.dataframe(query_result, width="stretch", height=400)` is rendered below the SQL panel, providing virtual scroll for large result sets and click-to-sort on column headers

#### Scenario: empty result set
- **WHEN** `query_result` is `None`, an empty list, or absent
- **THEN** no dataframe is rendered (the backend will have set `error_message`, which `error-display` surfaces)

---

### Requirement: error-display
All error conditions SHALL be surfaced as `st.warning` messages. No raw JSON, stack traces, or HTTP status codes SHALL be shown to the user.

#### Scenario: backend returns error_message
- **WHEN** the response JSON contains a non-None `error_message`
- **THEN** `st.warning(error_message)` is rendered; no SQL panel or dataframe is shown

#### Scenario: network or connection failure
- **WHEN** the HTTP request raises an `httpx.ConnectError` or any `httpx.RequestError`
- **THEN** `st.warning("Could not connect to the server. Please try again.")` is shown; page state is otherwise unchanged

#### Scenario: usable after failure
- **WHEN** any error condition (backend error, network error) has been displayed
- **THEN** the question input and submit button remain available; the user can immediately submit another question without reloading the page

---

### Requirement: future-fields-ignored
`insights`, `followup_questions`, `chart_config`, and `session_history` present in the response SHALL be silently ignored. The UI reads only `generated_sql`, `query_result`, and `error_message` in this slice.

#### Scenario: response contains future fields
- **WHEN** the response JSON contains non-None values for `insights`, `followup_questions`, or `chart_config`
- **THEN** the UI renders only the SQL panel and results table; no additional panels appear

### Requirement: csv-export

When the multi-row `st.dataframe` path is rendered (`query_result` is non-empty and the result is not a single scalar value), the UI SHALL render a `st.download_button` immediately below the dataframe that exports the full result set as a CSV file. The button SHALL be absent when no results are available and when the result is a single scalar value (1 row × 1 column, rendered as `st.metric`).

#### Scenario: results present — download button visible
- **WHEN** `query_result` is a non-empty list of dicts and the result is not a single scalar (i.e., it is not the case that `row_count == 1` and `len(columns) == 1`)
- **THEN** a `st.download_button` labelled "Download CSV" is rendered below the dataframe; clicking it downloads a file named `query_results_<YYYYMMDD_HHMMSS>.csv` (timestamp formatted at render time) containing all rows, with column headers, as UTF-8 CSV; `index` is not included in the CSV output

#### Scenario: results present — CSV content is exact
- **WHEN** the user clicks "Download CSV"
- **THEN** the downloaded bytes equal `pd.DataFrame(query_result).to_csv(index=False).encode("utf-8")`; no values are transformed or omitted

#### Scenario: no results — download button absent
- **WHEN** `query_result` is `None` or an empty list
- **THEN** no download button is rendered; the `error-display` requirement handles messaging

#### Scenario: single-scalar result — download button absent
- **WHEN** `query_result` is a non-empty list with exactly one row and one column (`row_count == 1` and `len(columns) == 1`), rendering `st.metric`
- **THEN** no download button is rendered below the metric widget

