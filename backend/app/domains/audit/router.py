"""API-32 audit route: ``GET /tickets/{id}/events``."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_actor, get_db, request_id_header
from app.common.request_context import RequestContext
from app.common.responses import ErrorResponse
from app.core.enums import EventScope, EventType
from app.domains.audit.schema import EventListResponse
from app.domains.audit.service import AuditService

router = APIRouter(tags=["Audit"])


def error_responses(*status_codes: int) -> dict[int, dict[str, object]]:
    return {code: {"model": ErrorResponse} for code in status_codes}


@router.get(
    "/tickets/{id}/events",
    response_model=EventListResponse,
    operation_id="api32ListEvents",
    summary="List audit events",
    responses=error_responses(401, 403, 404, 422, 503),
)
def list_events(
    ticket_id: Annotated[int, Path(alias="id", ge=1)],
    actor: Annotated[RequestContext, Depends(get_current_actor)],
    database: Annotated[Session, Depends(get_db)],
    _request_id: Annotated[UUID | None, Depends(request_id_header)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    event_type: Annotated[EventType | None, Query()] = None,
    scope: Annotated[EventScope | None, Query()] = None,
) -> EventListResponse:
    return AuditService(database).list_events(
        ticket_id,
        actor,
        event_type=event_type,
        scope=scope,
        page=page,
        page_size=page_size,
    )
