# Plan: results-table-csv-export

## Scope

Two files change. No backend, schema, agent, service, route, or repository changes.

| File | Change type |
|---|---|
| `website/app.py` | Modify — enhance table render + add download button |
| `tests/ui/test_app.py` | Modify — add 3 test functions for `csv-export` spec |

---

## Architecture Decisions

**No new imports beyond `pandas` and `datetime`.**
`website/app.py` already imports `uuid`, `httpx`, and `streamlit`. We add:
- `import pandas as pd` — needed for `pd.DataFrame(query_result).to_csv(index=False)`
- `from datetime import datetime` — for the `%Y%m%d_%H%M%S` timestamp in the filename

**Download button is in the multi-row `else:` branch only.**
The spec says "immediately below the results table." The single-scalar path renders `st.metric`, not a table — so no download button there. This also avoids a confusing "Download CSV" button next to a single-number metric.

**CSV generated in-process from `query_result` list-of-dicts.**
`pd.DataFrame(query_result).to_csv(index=False).encode("utf-8")` — the data is already serialized JSON in the UI; reconstructing a DataFrame purely for CSV output is the standard idiom and avoids a new API endpoint.

**Timestamp computed at render time.**
`datetime.now().strftime("%Y%m%d_%H%M%S")` is evaluated each time the page renders after a successful query. Re-renders within the same query response will produce the same timestamp (Streamlit re-runs the script synchronously) — this is acceptable behavior.

---

## Step-by-Step Implementation

### Step 1 — `website/app.py`

**1a. Add imports** (top of file, after `import uuid`):
```python
import pandas as pd
from datetime import datetime
```

**1b. Replace the `else:` branch** (current line 55):

Before:
```python
else:
    st.dataframe(query_result)
```

After:
```python
else:
    st.dataframe(
        query_result,
        use_container_width=True,
        height=400,
    )
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_bytes = (
        pd.DataFrame(query_result).to_csv(index=False).encode("utf-8")
    )
    st.download_button(
        label="Download CSV",
        data=csv_bytes,
        file_name=f"query_results_{timestamp}.csv",
        mime="text/csv",
    )
```

No other changes to `website/app.py`.

---

### Step 2 — `tests/ui/test_app.py`

Add a new section after the existing `# Tests — spec: results-display` block.

**Three new test functions** covering the three `csv-export` spec scenarios:

```python
# ---------------------------------------------------------------------------
# Tests — spec: csv-export
# ---------------------------------------------------------------------------


def test_csv_download_button_present_with_results() -> None:
    """Spec: results present — download button visible with label 'Download CSV'."""
    at = AppTest.from_file(APP_PATH)
    at.run()
    at.text_input[0].set_value("Show monthly sales")

    with patch("httpx.post", return_value=_mock_response(_success_data())):
        at.button[0].click()
        at.run()

    assert len(at.download_button) > 0
    assert any("Download CSV" in str(b.label) for b in at.download_button)


def test_csv_download_content_matches_query_result() -> None:
    """Spec: results present — CSV bytes equal pd.DataFrame(query_result).to_csv(index=False)."""
    import pandas as pd

    data = _success_data()

    at = AppTest.from_file(APP_PATH)
    at.run()
    at.text_input[0].set_value("Show monthly sales")

    with patch("httpx.post", return_value=_mock_response(data)):
        at.button[0].click()
        at.run()

    expected = pd.DataFrame(data["query_result"]).to_csv(index=False).encode("utf-8")
    download_btn = next(
        b for b in at.download_button if "Download CSV" in str(b.label)
    )
    assert download_btn.data == expected


def test_csv_download_button_absent_without_results() -> None:
    """Spec: no results — download button absent; error-display owns the messaging."""
    error_data = {
        "question": "Show dragon sales",
        "generated_sql": None,
        "query_result": None,
        "error_message": "Unable to identify requested entities.",
        "session_history": [],
    }

    at = AppTest.from_file(APP_PATH)
    at.run()
    at.text_input[0].set_value("Show dragon sales")

    with patch("httpx.post", return_value=_mock_response(error_data)):
        at.button[0].click()
        at.run()

    assert not any("Download CSV" in str(b.label) for b in at.download_button)
```

**Existing tests are unaffected.** The updated `st.dataframe(use_container_width=True, height=400)` call still renders a dataframe — `test_successful_response_shows_dataframe` asserts `len(at.dataframe) > 0`, which continues to pass. `test_single_scalar_result_shows_metric_not_dataframe` still passes because the single-scalar branch (`row_count == 1 and len(columns) == 1`) is untouched.

---

## Quality Gates (in order)

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

All three must pass before marking the change complete. No build step.

---

## Impact Summary

| Layer | Files touched | Nature |
|---|---|---|
| UI | `website/app.py` | Add 2 imports; update `st.dataframe` call; add `st.download_button` block |
| Tests | `tests/ui/test_app.py` | Add 3 test functions in new `csv-export` section |
| API / backend | — | No changes |
| Schemas | — | No changes |
| Agents / orchestration | — | No changes |

---

## Risk & Edge Cases

| Case | Handling |
|---|---|
| `query_result` is `[]` (empty list) | `if query_result:` is falsy for an empty list → neither dataframe nor download button renders. Backend will have set `error_message` for this path. |
| Single-scalar result (`row_count == 1, len(columns) == 1`) | Takes `st.metric` branch; no download button. Consistent with "immediately below the results table." |
| Very large result set | `pd.DataFrame(query_result).to_csv()` runs in-process. For datasets up to ~1M rows (NFR limit), this is acceptable; no streaming needed. |
| Multiple rapid queries | Each render generates a fresh `datetime.now()` timestamp, so successive exports have distinct filenames. |
| `at.download_button` accessor unavailable | Streamlit ≥1.18 is required (comment in test file confirms this project requires ≥1.58). `at.download_button` is available in all supported versions. |
