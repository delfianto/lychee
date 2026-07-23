"""Health check endpoint — the one example slice in the bare skeleton.

Real domain slices follow the ``router → service → repository`` layering
(see ../notes/decisions/02-backend-stack.md).
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}
