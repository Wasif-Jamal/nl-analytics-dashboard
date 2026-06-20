# Plan: streamlit-ui

## Context

Implements the Streamlit UI (`website/app.py`) as a pure API client for `POST /api/chat`, and extends `AnalyticsResponse` to carry serialized query rows. The UI is already scaffolded (stub with `st.set_page_config` + `st.title`). `streamlit>=1.58.0` and `httpx>=0.28.1` are already in `pyproject.toml` dependencies — no `uv add` required.

---

## Files

### Modified

| File | Change |
|---|---|
| `app/schemas/responses.py` | Add `query_result`, `columns`, `row_count` to `AnalyticsResponse` |
| `app/services/chat_service.py` | Serialize `QueryResult` into the three new fields in `ask()` |
| `website/app.py` | Replace stub with full Streamlit UI |
| `tests/services/test_chat_service.py` | Add two serialization tests |

### Created

| File | Change |
|---|---|
| `tests/ui/__init__.py` | Empty package marker |
| `tests/ui/test_app.py` | `AppTest`-based UI tests (10 scenarios) |

No new dependencies. No DB changes. No route changes. No migration.

---

## Step 1 — `app/schemas/responses.py`

Add three `Optional` fields to `AnalyticsResponse`, all defaulting to `None`. Additive only — all existing callers and tests remain valid.

```python
query_result: Optional[list[dict]] = None   # serialized rows
columns: Optional[list[str]] = None         # column names in result order
row_count: Optional[int] = None             # number of rows returned
```

Update the class docstring to document the new attributes.

**Why `list[dict]` not `QueryResult`:** `QueryResult` holds a `pd.DataFrame` and is not JSON-serializable; `to_dict(orient="records")` is the standard Pandas idiom and produces a structure `st.dataframe` accepts directly.

---

## Step 2 — `app/services/chat_service.py`

In the success branch of `ask()`, after the graph call returns and before constructing `AnalyticsResponse`, extract and serialize `query_result` from state:

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

Pass all three to `AnalyticsResponse(... query_result=serialized_rows, columns=columns, row_count=row_count)`.

**Error path:** the except branch already returns an `AnalyticsResponse` without the new fields — they default to `None`, so no change needed there.

---

## Step 3 — `website/app.py`

Replace the current stub. The app follows the Streamlit scripting model (functional — permitted by CLAUDE.md §10 for thin entry points).

**Structure:**

```python
API_BASE_URL = "http://localhost:8000"   # single constant; trivially configurable later

st.set_page_config(page_title="Natural Language Analytics Dashboard")
st.title("Natural Language Analytics Dashboard")

# Session UUID — generated once, persisted across reruns
if "session_uuid" not in st.session_state:
    st.session_state.session_uuid = str(uuid.uuid4())

question = st.text_input("Ask a question about your data")
submitted = st.button("Submit")

if submitted:
    if not question.strip():
        st.info("Please enter a question")
    else:
        with st.spinner("Analyzing..."):
            try:
                response = httpx.post(
                    f"{API_BASE_URL}/api/chat",
                    json={"session_uuid": st.session_state.session_uuid, "question": question},
                    timeout=60.0,
                )
                data = response.json()
                error_message = data.get("error_message")
                if error_message:
                    st.warning(error_message)
                else:
                    generated_sql = data.get("generated_sql")
                    if generated_sql:
                        with st.expander("Generated SQL"):
                            st.code(generated_sql, language="sql")
                    query_result = data.get("query_result")
                    if query_result:
                        st.dataframe(query_result)
            except httpx.ConnectError:
                st.warning("Could not connect to the server. Please try again.")
            except httpx.RequestError:
                st.warning("Could not connect to the server. Please try again.")
```

**Imports:** `uuid`, `httpx`, `streamlit as st`.

**Design notes:**
- `future fields ignored`: `insights`, `followup_questions`, `chart_config`, `session_history` are present in the response JSON but not read or rendered.
- `usable after failure`: Streamlit re-renders on each rerun; since state is not modified on error, the input and button are always available.
- `httpx.ConnectError` is the specific exception for unreachable hosts; `httpx.RequestError` is the base for all transport-level failures (timeout, etc.). Both map to the same user-facing message.
- `timeout=60.0` matches the FRS NFR of < 10 s typical, but allows headroom for slow queries.

---

## Step 4 — `tests/services/test_chat_service.py`

Add two tests after the existing block, using the existing `_make_state` helper, `service` fixture, and `_run` wrapper. Import `pd` and `QueryResult` from `app/schemas/sql_result`.

### New test: query_result serialized
```
mock_graph.invoke returns state with query_result = QueryResult(
    dataframe=pd.DataFrame([{"month": "Jan", "sales": 1000}]),
    columns=["month", "sales"],
    row_count=1
)
→ resp.query_result == [{"month": "Jan", "sales": 1000}]
→ resp.columns == ["month", "sales"]
→ resp.row_count == 1
```

### New test: query_result None when absent
```
mock_graph.invoke returns state with query_result=None
→ resp.query_result is None
→ resp.columns is None
→ resp.row_count is None
```

---

## Step 5 — `tests/ui/__init__.py`

Empty file.

---

## Step 6 — `tests/ui/test_app.py`

Uses `streamlit.testing.v1.AppTest` (available in Streamlit ≥ 1.18; we have ≥ 1.58) and `unittest.mock.patch`. No additional dependencies required.

**Constant:** `APP_PATH = "website/app.py"` at module level.

**Helper:**
```python
def _mock_response(data: dict) -> MagicMock:
    m = MagicMock()
    m.json.return_value = data
    return m

def _success_data(question="Show monthly sales") -> dict:
    return {
        "question": question,
        "generated_sql": "SELECT month, SUM(sales) FROM orders GROUP BY month",
        "query_result": [{"month": "Jan", "sales": 1000}],
        "columns": ["month", "sales"],
        "row_count": 1,
        "error_message": None,
        "session_history": [question],
    }
```

**Tests (spec scenario → test name):**

| Spec scenario | Test name |
|---|---|
| session-initialisation: first page load | `test_session_uuid_generated_on_first_load` |
| session-initialisation: subsequent interactions | `test_session_uuid_stable_across_reruns` |
| question-submission: empty question | `test_empty_question_shows_info_prompt` |
| question-submission: whitespace-only | `test_whitespace_question_shows_info_prompt` |
| sql-display: SQL present | `test_successful_response_shows_sql_expander` |
| results-display: rows present | `test_successful_response_shows_dataframe` |
| sql-display: SQL absent | `test_no_sql_expander_when_generated_sql_none` |
| error-display: backend error_message | `test_backend_error_message_shows_warning` |
| error-display: network failure | `test_connection_error_shows_warning` |
| error-display: usable after failure | `test_usable_after_network_error` |

**Patching convention:** `patch("httpx.post", ...)` wraps the `at.run()` call that triggers the submission — the patch is active during the script's execution of `httpx.post(...)`.

---

## Step 7 — Quality Gates

Run in order; all must be green before committing:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

No build step for Streamlit.

---

## Commit Strategy

Per feedback memory (commit per phase): two commits.

1. **`feat(responses): add query_result fields to AnalyticsResponse + ChatService serialization`**
   — `app/schemas/responses.py`, `app/services/chat_service.py`, updated `tests/services/test_chat_service.py`

2. **`feat(ui): implement Streamlit web UI and UI tests`**
   — `website/app.py`, `tests/ui/__init__.py`, `tests/ui/test_app.py`

---

## Open Questions / Risks

None — all decisions locked in via spec review. The `streamlit.testing.v1` module is stable API in Streamlit 1.18+; the test strategy is sound.
