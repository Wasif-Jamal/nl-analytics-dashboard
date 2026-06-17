"""Streamlit UI entry point.

The dashboard front end. It is a client of the backend FastAPI API
(``app/main.py``) — it calls the API routes rather than invoking the
workflow in-process. Run with ``uv run streamlit run website/app.py``.
"""

import streamlit as st

st.set_page_config(page_title="Natural Language Analytics Dashboard")
st.title("Natural Language Analytics Dashboard")
