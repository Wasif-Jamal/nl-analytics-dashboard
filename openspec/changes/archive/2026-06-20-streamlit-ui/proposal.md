## Why

The SQL pipeline (issue #1) and FastAPI layer (issue #2) are in place, but there is no way for a business user to reach them. This change delivers `website/app.py` — the first usable end-to-end slice of the product. A user types a plain-English question, the app posts to `POST /api/chat`, and the returned SQL and result rows are displayed in the browser. This is the moment the product becomes demonstrable.

The change also closes a gap in the existing API contract: `AnalyticsResponse` (defined in issue #2) does not include the raw query rows. Without them, the Streamlit UI has no data to put in `st.dataframe`. This issue extends the response schema and updates `ChatService` accordingly.

## What Changes

- **`app/schemas/responses.py`** — `AnalyticsResponse` extended with three new `Optional` fields: `query_result: Optional[list[dict]]` (serialized rows), `columns: Optional[list[str]]` (column names), `row_count: Optional[int]`. Defaults to `None` so all existing callers and tests are unaffected.
- **`app/services/chat_service.py`** — `ChatService.ask()` updated: when `query_result` is set in workflow state, serializes `QueryResult.dataframe.to_dict(orient="records")` and populates the three new response fields before returning.
- **`website/app.py`** — new Streamlit entry point (pure API client). On first load generates a `session_uuid` (UUID4) stored in `st.session_state`. On submit, POSTs `{session_uuid, question}` to `http://localhost:8000/api/chat` with a loading spinner. Renders: SQL in a collapsible `st.expander` + `st.code`, rows in `st.dataframe`, errors in `st.warning`. Remains usable after any failure.
- **Tests** — unit tests for the extended `ChatService` serialization logic (`tests/services/test_chat_service.py` updated); Streamlit UI tests for submission, error paths, and empty-question guard (`tests/ui/test_app.py`).

## Capabilities

### New Capabilities

- `streamlit-ui`: Browser-accessible question input → SQL display + results table. Generates and persists `session_uuid` across requests. Handles all three error scenarios from the issue spec: backend `error_message`, network failure, and empty-question submission.

### Modified Capabilities

- `response-schema` (api-layer-fastapi) — `AnalyticsResponse` gains `query_result`, `columns`, `row_count`. Additive only; existing contract unchanged.
- `chat-service-workflow-bridge` (api-layer-fastapi) — `ChatService.ask()` maps `QueryResult.dataframe` to the new response fields.

## Design Decisions

- **Hardcoded backend URL `http://localhost:8000`**: Chosen for simplicity at this stage. The URL is defined as a single constant `API_BASE_URL = "http://localhost:8000"` at the top of `website/app.py` so it is trivially configurable later without touching logic.
- **`query_result` as `list[dict]`**: DataFrames are not JSON-serializable; `to_dict(orient="records")` is the standard Pandas idiom and produces the structure `st.dataframe` accepts directly. `columns` and `row_count` are included so the UI can display metadata without re-deriving it.
- **Silently ignore future fields**: `insights`, `followup_questions`, `chart_config`, `session_history` may be non-None in the response (if the backend is fully wired) but are not rendered. The UI reads only `generated_sql`, `query_result`, `columns`, and `error_message`. Later issues add their panels.
- **`st.spinner` for loading**: Queries can take several seconds. The spinner runs for the full duration of the HTTP call; it is dismissed automatically whether the call succeeds or fails.
- **All errors → `st.warning`**: Both `error_message` in the response and caught `requests.ConnectionError` / `requests.RequestException` render as `st.warning`. No raw JSON or tracebacks are shown to the user.

## Impact

- New files: `website/app.py`, `tests/ui/__init__.py`, `tests/ui/test_app.py`.
- Modified: `app/schemas/responses.py` (additive fields), `app/services/chat_service.py` (serialization step).
- No changes to routes, agents, orchestration, or repositories.
