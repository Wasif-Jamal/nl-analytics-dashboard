# Tasks: results-table-csv-export

Two files change. No foundation work (no schemas, models, or DB changes).

---

## Phase 1: Foundation

> Nothing to do — this change requires no new Pydantic schemas, SQLAlchemy models,
> or DB init changes. `query_result`, `columns`, and `row_count` are already in
> `AnalyticsResponse`. Proceed directly to Phase 2.

---

## Phase 2: Core Implementation — `website/app.py`

- [ ] **2.1** Add `import pandas as pd` and `from datetime import datetime` to the import block at the top of `website/app.py` (after the existing `import uuid` line).

- [ ] **2.2** Replace the bare `st.dataframe(query_result)` call in the multi-row `else:` branch with `st.dataframe(query_result, use_container_width=True, height=400)`.

- [ ] **2.3** Immediately after the updated `st.dataframe` call, add the `st.download_button` block:
  ```python
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

**Checkpoint after Phase 2:**
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```
All existing UI tests must stay green before proceeding.

---

## Phase 3: Integration

> No integration wiring needed — `website/app.py` is a pure API client and the
> `query_result` field is already in the API response. Phase 3 is satisfied by the
> Phase 2 checkpoint passing.

---

## Phase 4: Tests — `tests/ui/test_app.py`

Add a new `# Tests — spec: csv-export` section. One test per spec scenario.

- [ ] **4.1** `test_csv_download_button_present_with_results` — spec scenario: *results present — download button visible*. Use `_success_data()` (2-column result), assert `len(at.download_button) > 0` and label is `"Download CSV"`.

- [ ] **4.2** `test_csv_download_content_matches_query_result` — spec scenario: *results present — CSV content is exact*. Assert `download_btn.data == pd.DataFrame(data["query_result"]).to_csv(index=False).encode("utf-8")`.

- [ ] **4.3** `test_csv_download_button_absent_without_results` — spec scenario: *no results — download button absent*. Use an error-path response (`query_result: None`, `error_message` set). Assert no download button with label `"Download CSV"` is rendered.

**Checkpoint after Phase 4 (final gate):**
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```
All tests — existing and new — must pass before marking this change complete.
