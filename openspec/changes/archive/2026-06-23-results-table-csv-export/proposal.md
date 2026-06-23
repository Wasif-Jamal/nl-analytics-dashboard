## Why

FR-5 and FR-12 require the results table to support sorting and CSV export. The current `results-display` spec (streamlit-ui) renders `st.dataframe(query_result)` with no fixed height, no sorting affordance, and no export capability. This change makes the table a first-class data-exploration surface: native column sorting and virtual scrolling via a fixed-height `st.dataframe`, plus a timestamped CSV download button that exports the full result set.

No API changes are needed — `query_result`, `columns`, and `row_count` are already in `AnalyticsResponse` (api-layer-fastapi spec).

## What Changes

- **`website/app.py`** — `results-display` block updated to `st.dataframe(query_result, use_container_width=True, height=400)`, enabling virtual scroll and native column-header sorting. A `st.download_button` is rendered immediately below the table when `query_result` is non-empty; the download produces `query_results_<YYYYMMDD_HHMMSS>.csv` containing all rows. The button is absent when `query_result` is `None` or empty.
- **`tests/ui/test_app.py`** — new scenarios: download button present with results (verifying CSV byte content matches the result set), button absent without results.

## Capabilities

### Modified Capabilities

- `results-display` (streamlit-ui) — table rendered with `height=400` and `use_container_width=True`, enabling virtual scroll for large result sets and native column-header click-to-sort. Pagination is implicit through virtual scrolling; no separate page controls are added.

### New Capabilities

- `csv-export` (streamlit-ui) — `st.download_button` appears below the results table when data is present. Clicking it downloads `query_results_<YYYYMMDD_HHMMSS>.csv` containing all rows from the current result set. The button is absent (not disabled) when no results are available; the existing `error-display` requirement already handles the no-data messaging.

## Design Decisions

- **Native `st.dataframe` for sorting and scroll**: Streamlit's `st.dataframe` supports column-header click-to-sort and virtual scrolling out of the box. Explicit prev/next pagination controls add UI complexity and test surface without meaningful benefit for typical business query sizes (hundreds to low thousands of rows).
- **Timestamped filename (`query_results_<YYYYMMDD_HHMMSS>.csv`)**: Multiple exports in one session would silently overwrite a static `results.csv` in the user's downloads folder. A timestamp suffix avoids this without server-side state.
- **Export scope = full result set**: The download button exports all rows from `query_result`, not just the visible portion. The user's intent when clicking "Export" is to take away the complete dataset.
- **No explicit empty-table message**: When `query_result` is `None` or empty, the backend sets `error_message` (e.g. `"No data found for the requested query."`), which `error-display` renders as `st.warning`. Adding a separate empty-table state would duplicate that signal.
- **CSV generated client-side from `query_result`**: `pd.DataFrame(query_result).to_csv(index=False)` converts the already-serialized list-of-dicts back into bytes for the download button. This avoids adding a new backend endpoint; FR-12 traces to "Streamlit download action over query result DataFrame" in SDS §15.

## Impact

- Modified: `website/app.py` (table height + download button), `tests/ui/test_app.py` (export scenarios).
- No changes to routes, schemas, agents, services, orchestration, or repositories.
