"""Streamlit UI entry point.

The dashboard front end. It is a pure API client of the backend FastAPI API
(``POST /api/chat``) — it calls the API routes and never imports LangGraph or
the ``app/`` package directly. Run with ``uv run streamlit run website/app.py``.
"""

import uuid

import httpx
import streamlit as st

API_BASE_URL = "http://localhost:8000"

st.set_page_config(page_title="Natural Language Analytics Dashboard")
st.title("Natural Language Analytics Dashboard")

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
                    json={
                        "session_uuid": st.session_state.session_uuid,
                        "question": question,
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
                    query_result = data.get("query_result")
                    if query_result:
                        st.dataframe(query_result)
            except httpx.ConnectError:
                st.warning("Could not connect to the server. Please try again.")
            except httpx.RequestError:
                st.warning("Could not connect to the server. Please try again.")
