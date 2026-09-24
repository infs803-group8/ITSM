"""API-21 route: ``POST /tickets/{id}/assign`` (Assign/Reassign, C024)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_actor, get_db, request_id_header
from app.common.request_context import RequestContext
from app.common.responses import ErrorResponse
from app.core.clock import utc_now
from app.domains.assignment.schema import AssignmentRequest, TicketActionResponse
from app.domains.assignment.service import AssignTicketService
from app.domains.workflow.router import build_ticket_action_response
from app.domains.workflow.schema import AvailableAction

router = APIRouter(tags=["Workflow"])


def error_responses(*status_codes: int) -> dict[int, dict[str, object]]:
    return {code: {"model": ErrorResponse} for code in status_codes}


@router.post(
    "/tickets/{id}/assign",
    response_model=TicketActionResponse,
    operation_id="api21AssignTicket",
    summary="Assign/reassign",
    responses=error_responses(401, 403, 404, 409, 422, 503),
)
def assign_ticket(
    ticket_id: Annotated[int, Path(alias="id", ge=1)],
    body: AssignmentRequest,
    actor: Annotated[RequestContext, Depends(get_current_actor)],
    database: Annotated[Session, Depends(get_db)],
    _request_id: Annotated[UUID | None, Depends(request_id_header)],
) -> TicketActionResponse:
    outcome = AssignTicketService(database).assign_ticket(
        ticket_id=ticket_id,
        actor=actor,
        assignee_id=body.assignee_id,
        reason=body.reason,
        now=utc_now(),
    )
    database.commit()
    return build_ticket_action_response(
        database,
        ticket_id=ticket_id,
        actor=actor,
        action=AvailableAction.ASSIGN,
        event_id=outcome.event_id,
    )
