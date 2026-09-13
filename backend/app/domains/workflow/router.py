"""Write-path workflow action routes (C025 onward).

Implemented exactly as docs/api/openapi.yaml specifies per operation.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_actor, get_db, request_id_header
from app.common.request_context import RequestContext
from app.common.responses import ErrorResponse
from app.core.enums import UserRole
from app.core.errors import ApplicationError
from app.domains.workflow.schema import AvailableAction, TicketActionData, TicketActionResponse
from app.domains.workflow.serializer import ActorContext
from app.domains.workflow.service import StartTicketService
from app.domains.workflow.ticket_detail import assemble_ticket_detail

router = APIRouter(tags=["Workflow"])


def error_responses(*status_codes: int) -> dict[int, dict[str, object]]:
    return {code: {"model": ErrorResponse} for code in status_codes}


def _respond(
    database: Session, *, ticket_id: int, actor: RequestContext, action: AvailableAction, event_id: int
) -> TicketActionResponse:
    """Shared response assembly for every action in this router: build the
    fresh, post-write TicketDetail (same read C021's WorkflowReadModel
    powers API-17 with) and wrap it in a TicketActionData.
    """
    actor_context = ActorContext(
        role=UserRole(actor.role), user_id=actor.user_id, vendor_org_id=actor.vendor_org_id
    )
    ticket = assemble_ticket_detail(database, ticket_id=ticket_id, actor=actor_context)
    if ticket is None:
        raise ApplicationError("RESOURCE_NOT_FOUND", "The requested resource was not found.", 404)
    return TicketActionResponse(
        data=TicketActionData(
            action=action,
            ticket=ticket,
            event_id=event_id,
            comment_id=None,
            vendor_request=None,
            vendor_response=None,
        )
    )


@router.post(
    "/tickets/{id}/start",
    response_model=TicketActionResponse,
    operation_id="api22StartTicket",
    summary="Start handling",
    responses=error_responses(401, 403, 404, 409, 503),
)
def start_ticket(
    ticket_id: Annotated[int, Path(alias="id", ge=1)],
    actor: Annotated[RequestContext, Depends(get_current_actor)],
    database: Annotated[Session, Depends(get_db)],
    _request_id: Annotated[UUID | None, Depends(request_id_header)],
) -> TicketActionResponse:
    outcome = StartTicketService(database).start(ticket_id=ticket_id, actor=actor)
    database.commit()
    return _respond(
        database, ticket_id=ticket_id, actor=actor, action=AvailableAction.START, event_id=outcome.event_id
    )
