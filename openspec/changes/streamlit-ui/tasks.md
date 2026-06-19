## 1. Phase 1 — Schema Extension

- [x] 1.1 `app/schemas/responses.py` — extend `AnalyticsResponse`
  - [x] 1.1.1 Add `query_result: Optional[list[dict]] = None` — serialized rows from `QueryResult.dataframe.to_dict(orient="records")`
  - [x] 1.1.2 Add `columns: Optional[list[str]] = None` — column names in result order
  - [x] 1.1.3 Add `row_count: Optional[int] = None` — number of rows returned
  - [x] 1.1.4 Update class docstring to document the three new attributes

**Checkpoint:**
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## 2. Phase 2 — Core Implementation

Tasks 2.1 and 2.2 are independent once Phase 1 is done — **[PARALLEL]**.

### 2.1 **[PARALLEL]** `app/services/chat_service.py` — serialize `QueryResult` *(depends on 1.1)*

- [x] 2.1.1 In the success branch of `ask()`, after reading `error_message` from state, extract and serialize `query_result`:
  ```python
  query_result_obj = result.get("query_result")
  serialized_rows: list[dict] | None = None
  columns: list[str] | None = None
  row_count: int | None = None
  if query_result_obj is not None:
      serialized_rows = query_result_obj.dataframe.to_dict(orient="records")
      columns = query_result_obj.columns
      row_count = query_result_obj.row_count
  ```
- [x] 2.1.2 Pass `query_result=serialized_rows, columns=columns, row_count=row_count` to the `AnalyticsResponse(...)` constructor
- [x] 2.1.3 Update the `ask()` docstring to mention the serialization step
- [x] 2.1.4 Verify the `except` branch is unchanged — `query_result`, `columns`, `row_count` are absent from that `AnalyticsResponse(...)` call so they correctly default to `None`

### 2.2 **[PARALLEL]** `website/app.py` — full Streamlit UI *(depends on 1.1)*

- [x] 2.2.1 Add imports: `import uuid`, `import httpx`, `import streamlit as st`
- [x] 2.2.2 Define module-level constant: `API_BASE_URL = "http://localhost:8000"`
- [x] 2.2.3 Keep existing `st.set_page_config(page_title="Natural Language Analytics Dashboard")` and `st.title(...)` calls at the top
- [x] 2.2.4 Session init — generate UUID once:
  ```python
  if "session_uuid" not in st.session_state:
      st.session_state.session_uuid = str(uuid.uuid4())
  ```
- [x] 2.2.5 Add question text input: `question = st.text_input("Ask a question about your data")`
- [x] 2.2.6 Add submit button: `submitted = st.button("Submit")`
- [x] 2.2.7 Empty/whitespace guard — when `submitted` and `not question.strip()`: show `st.info("Please enter a question")`; no HTTP call is made
- [x] 2.2.8 Happy-path submission — when `submitted` and `question.strip()`:
  - Wrap the entire HTTP call in `with st.spinner("Analyzing...")`
  - `httpx.post(f"{API_BASE_URL}/api/chat", json={"session_uuid": st.session_state.session_uuid, "question": question}, timeout=60.0)`
  - Read `data = response.json()`
- [x] 2.2.9 Response rendering — error branch: if `data.get("error_message")` → `st.warning(error_message)`
- [x] 2.2.10 Response rendering — success branch:
  - If `data.get("generated_sql")` → `st.expander("Generated SQL")` containing `st.code(generated_sql, language="sql")`
  - If `data.get("query_result")` → `st.dataframe(query_result)`
- [x] 2.2.11 Network error handling:
  - `except httpx.ConnectError` → `st.warning("Could not connect to the server. Please try again.")`
  - `except httpx.RequestError` → `st.warning("Could not connect to the server. Please try again.")`
- [x] 2.2.12 Add module docstring (states it is a pure API client, references `POST /api/chat`, run command)

**Checkpoint:**
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## 3. Phase 3 — Tests

Tasks 3.1 and 3.2 are independent — **[PARALLEL]**.

### 3.1 **[PARALLEL]** `tests/services/test_chat_service.py` — add serialization tests *(spec: chat-service-workflow-bridge — query_result)*

- [x] 3.1.1 Add imports at top: `import pandas as pd` and `from app.schemas.sql_result import QueryResult`

- [x] 3.1.2 *(spec: response-schema — successful workflow: query_result populated)*
  `test_query_result_serialized_in_response`:
  - Build `QueryResult(dataframe=pd.DataFrame([{"month": "Jan", "sales": 1000}]), columns=["month", "sales"], row_count=1)`
  - `mock_graph.invoke.return_value = _make_state(query_result=<above>)`
  - Assert `resp.query_result == [{"month": "Jan", "sales": 1000}]`
  - Assert `resp.columns == ["month", "sales"]`
  - Assert `resp.row_count == 1`

- [x] 3.1.3 *(spec: response-schema — workflow error: query_result absent)*
  `test_query_result_none_when_absent`:
  - `mock_graph.invoke.return_value = _make_state(query_result=None)`
  - Assert `resp.query_result is None`
  - Assert `resp.columns is None`
  - Assert `resp.row_count is None`

### 3.2 **[PARALLEL]** `tests/ui/` — Streamlit UI tests *(spec: streamlit-ui — all scenarios)*

- [x] 3.2.0 Create `tests/ui/__init__.py` — empty package marker

- [x] 3.2.1 Create `tests/ui/test_app.py` with:
  - `from streamlit.testing.v1 import AppTest`
  - `from unittest.mock import MagicMock, patch`
  - `APP_PATH = "website/app.py"` module-level constant
  - Helpers: `_mock_response(data: dict) -> MagicMock` and `_success_data(question="Show monthly sales") -> dict`

- [x] 3.2.2 *(spec: session-initialisation — first page load)*
  `test_session_uuid_generated_on_first_load`

- [x] 3.2.3 *(spec: session-initialisation — subsequent interactions)*
  `test_session_uuid_stable_across_reruns`

- [x] 3.2.4 *(spec: question-submission — empty question submitted)*
  `test_empty_question_shows_info_prompt`

- [x] 3.2.5 *(spec: question-submission — whitespace-only question)*
  `test_whitespace_question_shows_info_prompt`

- [x] 3.2.6 *(spec: sql-display — SQL present in response)*
  `test_successful_response_shows_sql_expander`

- [x] 3.2.7 *(spec: results-display — rows present in response)*
  `test_successful_response_shows_dataframe`

- [x] 3.2.8 *(spec: sql-display — SQL absent in response)*
  `test_no_sql_expander_when_generated_sql_none`

- [x] 3.2.9 *(spec: error-display — backend returns error_message)*
  `test_backend_error_message_shows_warning`

- [x] 3.2.10 *(spec: error-display — network / connection failure)*
  `test_connection_error_shows_warning`

- [x] 3.2.11 *(spec: error-display — usable after failure)*
  `test_usable_after_network_error`

**Checkpoint (final gate):**
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

---

## 4. Phase 4 — Finalize

- [x] 4.1 `openspec validate streamlit-ui` passes
- [x] 4.2 All quality gates green; any deviations from the plan reconciled into `plan.md`
