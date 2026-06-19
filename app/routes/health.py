"""FastAPI health router — liveness check endpoint.

Exposes ``GET /api/health`` with no dependencies. Safe to call before the
workflow is ready; used by load balancers and monitoring tools.
"""

from fastapi import APIRouter

from app.schemas.responses import HealthResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Return a liveness confirmation.

    Returns:
        ``HealthResponse(status="ok")`` unconditionally.
    """
    return HealthResponse(status="ok")
