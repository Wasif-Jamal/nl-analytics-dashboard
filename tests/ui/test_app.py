"""Streamlit UI tests for website/app.py.

Uses ``streamlit.testing.v1.AppTest`` (available since Streamlit 1.18; this
project requires >=1.58) and ``unittest.mock.patch`` to intercept ``httpx.post``
calls so no real backend is required. Each test maps 1:1 to a spec scenario in
the streamlit-ui spec.
"""

from unittest.mock import MagicMock, patch

import httpx
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import UnknownElement

APP_PATH = "website/app.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(data: dict) -> MagicMock:
    """Return a MagicMock whose .json() returns *data*."""
    m = MagicMock()
    m.json.return_value = data
    return m


def _find_unknown_elements(node, label: str) -> list:
    """Recursively find UnknownElement nodes with the given label."""
    results = []
    for child in node.children.values():
        if (
            isinstance(child, UnknownElement)
            and getattr(child.proto, "label", "") == label
        ):
            results.append(child)
        if hasattr(child, "children"):
            results.extend(_find_unknown_elements(child, label))
    return results


def _download_buttons(at: AppTest) -> list:
    """Return UnknownElements with label 'Download CSV' from the app tree."""
    return _find_unknown_elements(at.main, "Download CSV")


def _success_data(question: str = "Show monthly sales") -> dict:
    """Minimal success payload from POST /api/chat."""
    return {
        "question": question,
        "generated_sql": "SELECT month, SUM(sales) FROM orders GROUP BY month",
        "query_result": [{"month": "Jan", "sales": 1000}],
        "columns": ["month", "sales"],
        "row_count": 1,
        "error_message": None,
    }


def _submit(at: AppTest, question: str, mock_data: dict | None = None) -> None:
    """Submit a question via chat_input, optionally mocking the HTTP response."""
    if mock_data is not None:
        with patch("httpx.post", return_value=_mock_response(mock_data)):
            at.chat_input[0].set_value(question)
            at.run()
    else:
        at.chat_input[0].set_value(question)
        at.run()


# ---------------------------------------------------------------------------
# Tests — spec: session-initialisation
# ---------------------------------------------------------------------------


def test_session_uuid_generated_on_first_load() -> None:
    """Spec: first page load — session_uuid present in st.session_state."""
    at = AppTest.from_file(APP_PATH)
    at.run()

    assert "session_uuid" in at.session_state
    assert len(at.session_state["session_uuid"]) > 0


def test_session_uuid_stable_across_reruns() -> None:
    """Spec: subsequent interactions — same UUID used across reruns."""
    at = AppTest.from_file(APP_PATH)
    at.run()
    first_uuid = at.session_state["session_uuid"]
    at.run()
    second_uuid = at.session_state["session_uuid"]

    assert first_uuid == second_uuid


# ---------------------------------------------------------------------------
# Tests — spec: question-submission (chat layout)
# ---------------------------------------------------------------------------


def test_chat_input_present_on_load() -> None:
    """Spec: question-submission — st.chat_input widget present on first load."""
    at = AppTest.from_file(APP_PATH)
    at.run()

    assert len(at.chat_input) > 0


def test_chat_layout_user_message_rendered() -> None:
    """Spec: question-submission — user question rendered in the chat transcript."""
    at = AppTest.from_file(APP_PATH)
    at.run()

    _submit(at, "Show monthly sales", _success_data())

    assert any("Show monthly sales" in str(m.value) for m in at.markdown)


def test_turns_accumulated_in_session_state() -> None:
    """Spec: question-submission — each answered turn is appended to session_state.turns."""
    at = AppTest.from_file(APP_PATH)
    at.run()

    _submit(at, "Show monthly sales", _success_data("Show monthly sales"))
    assert len(at.session_state["turns"]) == 1
    assert at.session_state["turns"][0]["question"] == "Show monthly sales"

    _submit(at, "Show profit by region", _success_data("Show profit by region"))
    assert len(at.session_state["turns"]) == 2


# ---------------------------------------------------------------------------
# Tests — spec: sql-display
# ---------------------------------------------------------------------------


def test_successful_response_shows_sql_expander() -> None:
    """Spec: SQL present in response — st.expander with 'Generated SQL' label rendered."""
    at = AppTest.from_file(APP_PATH)
    at.run()

    _submit(at, "Show monthly sales", _success_data())

    assert len(at.expander) > 0
    assert any("Generated SQL" in str(e.label) for e in at.expander)


def test_no_sql_expander_when_generated_sql_none() -> None:
    """Spec: SQL absent in response — no st.expander rendered."""
    data = _success_data()
    data["generated_sql"] = None

    at = AppTest.from_file(APP_PATH)
    at.run()

    _submit(at, "Show monthly sales", data)

    assert len(at.expander) == 0


# ---------------------------------------------------------------------------
# Tests — spec: results-display
# ---------------------------------------------------------------------------


def test_successful_response_shows_dataframe() -> None:
    """Spec: rows present in response — st.dataframe rendered."""
    at = AppTest.from_file(APP_PATH)
    at.run()

    _submit(at, "Show monthly sales", _success_data())

    assert len(at.dataframe) > 0


def test_single_scalar_result_shows_written_answer_not_dataframe() -> None:
    """Single-column, single-row result with chart_config written_answer — st.info shown, no st.dataframe."""
    data = {
        "question": "How many customers do we have?",
        "generated_sql": "SELECT COUNT(DISTINCT customer_id) AS customer_count FROM customers",
        "query_result": [{"customer_count": 736}],
        "columns": ["customer_count"],
        "row_count": 1,
        "chart_config": {
            "chart_type": "table",
            "x_column": None,
            "y_column": None,
            "title": "",
            "written_answer": "Total distinct customers is 736.",
        },
        "error_message": None,
    }

    at = AppTest.from_file(APP_PATH)
    at.run()

    _submit(at, "How many customers do we have?", data)

    assert len(at.info) == 1
    assert "736" in at.info[0].value
    assert len(at.dataframe) == 0


# ---------------------------------------------------------------------------
# Tests — spec: error-display
# ---------------------------------------------------------------------------


def test_backend_error_message_shows_warning() -> None:
    """Spec: backend returns error_message — st.warning shown, no SQL or dataframe."""
    error_msg = "Unable to identify requested entities."
    data = {
        "question": "Show dragon sales",
        "generated_sql": None,
        "query_result": None,
        "error_message": error_msg,
    }

    at = AppTest.from_file(APP_PATH)
    at.run()

    _submit(at, "Show dragon sales", data)

    assert len(at.warning) > 0
    assert any(error_msg in str(w.value) for w in at.warning)
    assert len(at.expander) == 0
    assert len(at.dataframe) == 0


def test_connection_error_shows_warning() -> None:
    """Spec: network / connection error — 'Could not connect' warning shown."""
    at = AppTest.from_file(APP_PATH)
    at.run()

    with patch("httpx.post", side_effect=httpx.ConnectError("connection refused")):
        at.chat_input[0].set_value("Show monthly sales")
        at.run()

    assert len(at.warning) > 0
    assert any("Could not connect to the server" in str(w.value) for w in at.warning)


def test_usable_after_network_error() -> None:
    """Spec: usable after failure — chat_input still present after a connection error."""
    at = AppTest.from_file(APP_PATH)
    at.run()

    with patch("httpx.post", side_effect=httpx.ConnectError("connection refused")):
        at.chat_input[0].set_value("Show monthly sales")
        at.run()

    assert len(at.warning) > 0
    assert len(at.chat_input) > 0


# ---------------------------------------------------------------------------
# Tests — spec: csv-export
# ---------------------------------------------------------------------------


def test_csv_download_button_present_with_results() -> None:
    """Spec: results present — download button visible with label 'Download CSV'."""
    at = AppTest.from_file(APP_PATH)
    at.run()

    _submit(at, "Show monthly sales", _success_data())

    assert len(_download_buttons(at)) == 1


def test_csv_download_content_matches_query_result() -> None:
    """Spec: results present — CSV bytes equal pd.DataFrame(query_result).to_csv(index=False)."""
    import pandas as pd
    import streamlit as _st

    data = _success_data()
    expected = pd.DataFrame(data["query_result"]).to_csv(index=False).encode("utf-8")
    captured: dict = {}

    original_dl = _st.download_button

    def capture_and_call(**kwargs: object) -> object:
        captured.update(kwargs)
        return original_dl(**kwargs)

    at = AppTest.from_file(APP_PATH)
    at.run()

    with (
        patch("httpx.post", return_value=_mock_response(data)),
        patch.object(_st, "download_button", side_effect=capture_and_call),
    ):
        at.chat_input[0].set_value("Show monthly sales")
        at.run()

    assert captured.get("data") == expected
    assert captured.get("label") == "Download CSV"
    assert captured.get("mime") == "text/csv"
    assert str(captured.get("file_name", "")).startswith("query_results_")


def test_csv_download_button_absent_for_scalar_result() -> None:
    """Spec: single-scalar result with written_answer — st.info shown, no download button."""
    data = {
        "question": "How many customers do we have?",
        "generated_sql": "SELECT COUNT(DISTINCT customer_id) AS customer_count FROM customers",
        "query_result": [{"customer_count": 736}],
        "columns": ["customer_count"],
        "row_count": 1,
        "chart_config": {
            "chart_type": "table",
            "x_column": None,
            "y_column": None,
            "title": "",
            "written_answer": "Total distinct customers is 736.",
        },
        "error_message": None,
    }
    at = AppTest.from_file(APP_PATH)
    at.run()

    _submit(at, "How many customers do we have?", data)

    assert len(at.info) == 1
    assert len(_download_buttons(at)) == 0


def test_csv_download_button_absent_without_results() -> None:
    """Spec: no results — download button absent; error-display owns the messaging."""
    error_data = {
        "question": "Show dragon sales",
        "generated_sql": None,
        "query_result": None,
        "error_message": "Unable to identify requested entities.",
    }
    at = AppTest.from_file(APP_PATH)
    at.run()

    _submit(at, "Show dragon sales", error_data)

    assert len(_download_buttons(at)) == 0


# ---------------------------------------------------------------------------
# Tests — spec: chart-display
# ---------------------------------------------------------------------------


def test_chart_rendered_with_png_download_button() -> None:
    """Spec: chart_type=bar + build_figure returns figure — no dataframe, Download PNG button rendered."""
    data = {
        "question": "Show sales by month",
        "generated_sql": "SELECT month, SUM(sales) FROM orders GROUP BY month",
        "query_result": [
            {"month": "Jan", "sales": 1000},
            {"month": "Feb", "sales": 1200},
        ],
        "columns": ["month", "sales"],
        "row_count": 2,
        "chart_config": {
            "chart_type": "bar",
            "x_column": "month",
            "y_column": "sales",
            "title": "Sales by Month",
        },
        "error_message": None,
    }

    at = AppTest.from_file(APP_PATH)
    at.run()

    with (
        patch("httpx.post", return_value=_mock_response(data)),
        patch("plotly.io.to_image", return_value=b"fakepng"),
    ):
        at.chat_input[0].set_value("Show sales by month")
        at.run()

    # Chart path taken — dataframe and CSV download button absent
    assert len(at.dataframe) == 0
    assert len(_download_buttons(at)) == 0
    # Download PNG button rendered
    png_buttons = _find_unknown_elements(at.main, "Download PNG")
    assert len(png_buttons) == 1
    assert len(at.warning) == 0


def test_all_active_response_fields_rendered() -> None:
    """Spec: chart_config + insights + followup_questions all rendered, none dropped."""
    data = _success_data()
    data["chart_config"] = {"chart_type": "table", "title": ""}
    data["insights"] = ["Sales peaked in January."]
    data["followup_questions"] = ["What drove January sales?"]

    at = AppTest.from_file(APP_PATH)
    at.run()

    _submit(at, "Show monthly sales", data)

    # chart_config=table → dataframe rendered
    assert len(at.dataframe) == 1
    # insights rendered
    assert any("Insights" in str(s.value) for s in at.subheader)
    assert any("Sales peaked in January." in str(m.value) for m in at.markdown)
    # followup_questions rendered as Suggested Questions
    assert any("Suggested Questions" in str(s.value) for s in at.subheader)
    assert len(at.warning) == 0


# ---------------------------------------------------------------------------
# Tests — spec: future-fields-ignored
# ---------------------------------------------------------------------------


def test_chart_config_table_falls_back_to_dataframe() -> None:
    """Spec: chart_type=table with no written_answer renders dataframe; followup_questions shown as buttons."""
    data = _success_data()
    data["followup_questions"] = ["What drove January sales?"]
    data["chart_config"] = {"chart_type": "table", "title": ""}

    at = AppTest.from_file(APP_PATH)
    at.run()

    _submit(at, "Show monthly sales", data)

    # SQL expander and dataframe rendered; no errors.
    assert len(at.expander) == 1
    assert len(at.dataframe) == 1
    assert len(at.warning) == 0


# ---------------------------------------------------------------------------
# Tests — spec: insights-display
# ---------------------------------------------------------------------------


def test_insights_present_panel_rendered() -> None:
    """Spec: insights-display — non-empty insights rendered as subheader + bullets."""
    data = _success_data()
    data["insights"] = ["Sales peaked in January.", "March had the lowest margin."]

    at = AppTest.from_file(APP_PATH)
    at.run()

    _submit(at, "Show monthly sales", data)

    assert any("Insights" in str(s.value) for s in at.subheader)
    assert any("Sales peaked in January." in str(m.value) for m in at.markdown)
    assert any("March had the lowest margin." in str(m.value) for m in at.markdown)


def test_insights_absent_no_panel() -> None:
    """Spec: insights-display — no Insights panel when insights is None, [], or missing."""
    for insights_value in [None, [], "missing"]:
        data = _success_data()
        if insights_value == "missing":
            data.pop("insights", None)
        else:
            data["insights"] = insights_value

        at = AppTest.from_file(APP_PATH)
        at.run()

        _submit(at, "Show monthly sales", data)

        assert not any("Insights" in str(s.value) for s in at.subheader)


def test_insights_not_shown_on_error_path() -> None:
    """Spec: insights-display — insights panel absent when error_message is set."""
    data = {
        "question": "Show dragon sales",
        "generated_sql": None,
        "query_result": None,
        "error_message": "Unable to identify requested entities.",
        "insights": ["This insight should not appear."],
    }
    at = AppTest.from_file(APP_PATH)
    at.run()

    _submit(at, "Show dragon sales", data)

    assert len(at.warning) > 0
    assert not any("Insights" in str(s.value) for s in at.subheader)
