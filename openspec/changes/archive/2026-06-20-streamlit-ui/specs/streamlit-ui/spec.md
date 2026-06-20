# Spec: streamlit-ui

## Purpose

Defines the Streamlit web UI (`website/app.py`) — the sole entry point for business users. The UI is a pure API client: it calls `POST /api/chat` and never imports LangGraph or the `app/` package directly. This spec governs session initialisation, question submission, result rendering, error handling, and loading state for the first end-to-end slice of the product (FRS §6.1, §6.6, §11; FR-1, FR-5).

---

## ADDED Requirements

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
If the response contains a non-None `query_result`, the UI SHALL display the rows in a `st.dataframe` table.

#### Scenario: rows present in response
- **WHEN** `query_result` is a non-empty list of dicts in the response
- **THEN** `st.dataframe(query_result)` is rendered below the SQL panel

#### Scenario: empty result set
- **WHEN** `query_result` is `None`, an empty list, or absent
- **THEN** no dataframe is rendered (error message will have been set by the backend)

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
