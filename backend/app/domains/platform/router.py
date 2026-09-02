"""API-01 public platform route."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, request_id_header
from app.common.responses import ErrorResponse
from app.domains.platform.schema import HealthResponse
from app.domains.platform.service import PlatformService

router = APIRouter(tags=["System"])


@router.get(
    "/health",
    response_model=HealthResponse,
    operation_id="api01Health",
    summary="Backend health check",
    responses={503: {"model": ErrorResponse, "description": "Dependency unavailable."}},
)
def health(
    database: Annotated[Session, Depends(get_db)],
    _request_id: Annotated[UUID | None, Depends(request_id_header)],
) -> HealthResponse:
    return PlatformService().health(database)
