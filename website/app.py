"""Streamlit UI entry point.

The dashboard front end. It is a pure API client of the backend FastAPI API
(``POST /api/chat``) — it calls the API routes and never imports LangGraph or
the ``app/`` package directly. Run with ``uv run streamlit run website/app.py``.
"""

import uuid
from datetime import datetime

import httpx
import pandas as pd
import plotly.express as px
import streamlit as st

API_BASE_URL = "http://localhost:8000"

st.set_page_config(page_title="Natural Language Analytics Dashboard", layout="wide")
st.title("Natural Language Analytics Dashboard")

if "session_uuid" not in st.session_state:
    st.session_state.session_uuid = str(uuid.uuid4())

if "pending_question" not in st.session_state:
    st.session_state.pending_question = ""

pending = st.session_state.pending_question
auto_submit = bool(pending)
if auto_submit:
    st.session_state.pending_question = ""


_CHART_TYPES = {"bar", "line", "pie", "scatter"}


def _build_figure(chart_config: dict, rows: list[dict]):
    """Build a Plotly figure from the chart_config dict and query rows.

    Mirrors the logic of ``app.utils.chart_helpers.build_figure`` but operates
    on the plain dict returned by the API so ``website/app.py`` does not need to
    import from the ``app`` package (Streamlit places ``website/`` first on
    ``sys.path``, which would shadow the ``app`` package with this script).

    Returns a Plotly Figure or None.
    """
    chart_type = chart_config.get("chart_type")
    if chart_type not in _CHART_TYPES or not rows:
        return None
    x_col = chart_config.get("x_column")
    y_col = chart_config.get("y_column")
    title = chart_config.get("title", "")
    if x_col and x_col not in rows[0]:
        return None
    if y_col and y_col not in rows[0]:
        return None
    try:
        df = pd.DataFrame(rows)
        if chart_type == "bar":
            return px.bar(df, x=x_col, y=y_col, title=title)
        if chart_type == "line":
            return px.line(df, x=x_col, y=y_col, title=title)
        if chart_type == "pie":
            return px.pie(df, names=x_col, values=y_col, title=title)
        if chart_type == "scatter":
            return px.scatter(df, x=x_col, y=y_col, title=title)
    except Exception:
        return None
    return None


def _render_dataframe(query_result: list[dict], columns: list, row_count: int) -> None:
    """Render a dataframe with CSV download for multi-row results.

    Args:
        query_result: Rows as list of dicts from the API response.
        columns: Ordered column names.
        row_count: Number of rows returned.
    """
    if not query_result:
        return
    st.dataframe(query_result, width="stretch", height=400)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_bytes = pd.DataFrame(query_result).to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download CSV",
        data=csv_bytes,
        file_name=f"query_results_{timestamp}.csv",
        mime="text/csv",
    )


question = st.text_input("Ask a question about your data", value=pending)
submitted = st.button("Submit") or auto_submit

if submitted:
    effective_question = pending if auto_submit else question
    if not effective_question.strip():
        st.info("Please enter a question")
    else:
        with st.spinner("Analyzing..."):
            try:
                response = httpx.post(
                    f"{API_BASE_URL}/api/chat",
                    json={
                        "session_uuid": st.session_state.session_uuid,
                        "question": effective_question,
                    },
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

                    query_result = data.get("query_result") or []
                    columns = data.get("columns") or []
                    row_count = data.get("row_count") or 0
                    chart_config_dict = data.get("chart_config")

                    if chart_config_dict:
                        written_answer = chart_config_dict.get("written_answer")
                        chart_type = chart_config_dict.get("chart_type")

                        if written_answer:
                            # Single-value path: LLM-generated plain-language sentence
                            st.info(written_answer)

                        elif chart_type in _CHART_TYPES:
                            # Chart path: build and render Plotly figure
                            fig = _build_figure(chart_config_dict, query_result)
                            if fig:
                                st.plotly_chart(fig, width="stretch")
                                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                st.download_button(
                                    label="Download PNG",
                                    data=fig.to_image(format="png"),
                                    file_name=f"chart_{timestamp}.png",
                                    mime="image/png",
                                )
                            else:
                                _render_dataframe(query_result, columns, row_count)

                        else:
                            # Table-only path (chart_type="table", no written_answer)
                            _render_dataframe(query_result, columns, row_count)

                    elif query_result:
                        # Fallback: chart_config absent — use dataframe
                        _render_dataframe(query_result, columns, row_count)

                    insights = data.get("insights") or []
                    if insights:
                        st.subheader("Insights")
                        for insight in insights:
                            st.markdown(f"- {insight}")
                    followup_questions = data.get("followup_questions") or []
                    if followup_questions:
                        st.subheader("Suggested Questions")
                        for q in followup_questions:
                            if st.button(q, key=f"followup_{hash(q)}"):
                                st.session_state.pending_question = q
                                st.rerun()
            except httpx.ConnectError:
                st.warning("Could not connect to the server. Please try again.")
            except httpx.RequestError:
                st.warning("Could not connect to the server. Please try again.")
