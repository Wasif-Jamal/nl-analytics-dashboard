"""FastAPI ASGI entry point for the backend.

Assembles the FastAPI application and mounts the routers defined under
`app.routes`. The Streamlit UI (``website/app.py``) is a client of this API.
Served via Uvicorn, e.g. ``uv run uvicorn app.main:app``.
"""

from fastapi import FastAPI

app = FastAPI(title="Natural Language Analytics Dashboard API")

# Routers from app.routes (chat_routes, health) are included here as they land.
