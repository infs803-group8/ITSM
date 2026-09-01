"""Platform health endpoint."""

from datetime import UTC, datetime

from fastapi import APIRouter

from app.domains.platform.schema import HealthResponse

router = APIRouter(tags=["Platform"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", timestamp=datetime.now(UTC))
