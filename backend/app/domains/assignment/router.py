"""API-21 route: ``POST /tickets/{id}/assign`` (Assign/Reassign, C024)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_actor, get_db, request_id_header
from app.common.request_context import RequestContext
from app.common.responses import ErrorResponse
from app.core.clock import utc_now
from app.core.enums import UserRole
from app.core.errors import ApplicationError
from app.domains.assignment.schema import AssignmentRequest, TicketActionResponse
from app.domains.assignment.service import AssignTicketService
from app.domains.workflow.schema import AvailableAction, TicketActionData
from app.domains.workflow.serializer import ActorContext
from app.domains.workflow.ticket_detail import assemble_ticket_detail

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

    actor_context = ActorContext(
        role=UserRole(actor.role), user_id=actor.user_id, vendor_org_id=actor.vendor_org_id
    )
    ticket = assemble_ticket_detail(database, ticket_id=ticket_id, actor=actor_context)
    if ticket is None:
        # Should be unreachable: assign_ticket already 404s on a missing
        # ticket before writing anything, and nothing here deletes rows.
        raise ApplicationError("RESOURCE_NOT_FOUND", "The requested resource was not found.", 404)

    return TicketActionResponse(
        data=TicketActionData(
            action=AvailableAction.ASSIGN,
            ticket=ticket,
            event_id=outcome.event_id,
            comment_id=None,
            vendor_request=None,
            vendor_response=None,
        )
    )
