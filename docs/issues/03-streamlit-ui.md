## Requirement

A Streamlit web UI (`website/app.py`) where business users type a natural-language question, submit it to the FastAPI backend (issue #2), and see the generated SQL and result data. This is the first usable end-to-end slice of the product. Source: FRS §6.1, §6.6, §11; FR-1, FR-5.

> The UI is a pure API client — it calls the FastAPI `/ask` endpoint (issue #2) and never imports LangGraph or the `app/` package directly. Run with `uv run streamlit run website/app.py`.

## Acceptance Criteria

1. A text input and submit button on the main page.
2. On submit, the UI POSTs to the FastAPI backend with `{session_uuid, question}`.
3. The generated SQL (`generated_sql`) is displayed in a collapsible code panel.
4. The result rows (`query_result`) are displayed in a `st.dataframe` table.
5. If `error_message` is present in the response, it is shown as a `st.warning` — not as raw JSON or a stack trace.
6. A `session_uuid` (UUID4) is generated on first load and stored in `st.session_state`; it is sent with every request.
7. The app remains usable after a failed query — the user can immediately submit another question.

## Error Scenarios

| Trigger | Expected result |
|---|---|
| Backend returns `error_message` | Display the standard message in a `st.warning` box |
| Network / connection error (backend unreachable) | Show "Could not connect to the server. Please try again." |
| Empty question submitted | Submit action is a no-op with an inline prompt ("Please enter a question") |

## Out of Scope

- Charts and visualizations (issue #5).
- Insights panel (issue #6).
- Suggested follow-up questions (issue #7).
- Conversation history & chat layout (issue #9).
- CSV export (issue #4).
- Authentication / authorization (FRS §13).
