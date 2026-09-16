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
from app.domains.workflow.schema import (
    AvailableAction,
    EscalateRequest,
    RequestUserInfoRequest,
    ResumeRequest,
    TicketActionData,
    TicketActionResponse,
)
from app.domains.workflow.serializer import ActorContext
from app.domains.workflow.service import (
    EscalateTicketService,
    RequestUserInfoService,
    ResumeTicketService,
    StartTicketService,
)
from app.domains.workflow.ticket_detail import assemble_ticket_detail

router = APIRouter(tags=["Workflow"])


def error_responses(*status_codes: int) -> dict[int, dict[str, object]]:
    return {code: {"model": ErrorResponse} for code in status_codes}


def _respond(
    database: Session,
    *,
    ticket_id: int,
    actor: RequestContext,
    action: AvailableAction,
    event_id: int,
    comment_id: int | None = None,
) -> TicketActionResponse:
    """Shared response assembly for every action in this router: build the
    fresh, post-write TicketDetail (same read C021's WorkflowReadModel
    powers API-17 with) and wrap it in a TicketActionData.

    ``comment_id`` defaults to None -- only actions that also write a
    comment (Request User Info today) pass their outcome's comment_id
    through; every other action leaves it unset exactly as before.
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
            comment_id=comment_id,
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
        database,
        ticket_id=ticket_id,
        actor=actor,
        action=AvailableAction.START,
        event_id=outcome.event_id,
    )


@router.post(
    "/tickets/{id}/request-user-info",
    response_model=TicketActionResponse,
    operation_id="api23RequestUserInfo",
    summary="Request user info",
    responses=error_responses(401, 403, 404, 409, 422, 503),
)
def request_user_info(
    ticket_id: Annotated[int, Path(alias="id", ge=1)],
    body: RequestUserInfoRequest,
    actor: Annotated[RequestContext, Depends(get_current_actor)],
    database: Annotated[Session, Depends(get_db)],
    _request_id: Annotated[UUID | None, Depends(request_id_header)],
) -> TicketActionResponse:
    outcome = RequestUserInfoService(database).request_user_info(
        ticket_id=ticket_id, actor=actor, message=body.message
    )
    database.commit()
    return _respond(
        database,
        ticket_id=ticket_id,
        actor=actor,
        action=AvailableAction.REQUEST_USER_INFO,
        event_id=outcome.event_id,
        comment_id=outcome.comment_id,
    )


@router.post(
    "/tickets/{id}/resume",
    response_model=TicketActionResponse,
    operation_id="api24ResumeTicket",
    summary="Resume ticket",
    responses=error_responses(401, 403, 404, 409, 422, 503),
)
def resume_ticket(
    ticket_id: Annotated[int, Path(alias="id", ge=1)],
    body: ResumeRequest,
    actor: Annotated[RequestContext, Depends(get_current_actor)],
    database: Annotated[Session, Depends(get_db)],
    _request_id: Annotated[UUID | None, Depends(request_id_header)],
) -> TicketActionResponse:
    outcome = ResumeTicketService(database).resume(
        ticket_id=ticket_id, actor=actor, message=body.message
    )
    database.commit()
    return _respond(
        database,
        ticket_id=ticket_id,
        actor=actor,
        action=AvailableAction.RESUME,
        event_id=outcome.event_id,
        comment_id=outcome.comment_id,
    )


@router.post(
    "/tickets/{id}/escalate",
    response_model=TicketActionResponse,
    operation_id="api25EscalateTicket",
    summary="Escalate to Tier 2",
    responses=error_responses(401, 403, 404, 409, 422, 503),
)
def escalate_ticket(
    ticket_id: Annotated[int, Path(alias="id", ge=1)],
    body: EscalateRequest,
    actor: Annotated[RequestContext, Depends(get_current_actor)],
    database: Annotated[Session, Depends(get_db)],
    _request_id: Annotated[UUID | None, Depends(request_id_header)],
) -> TicketActionResponse:
    outcome = EscalateTicketService(database).escalate(
        ticket_id=ticket_id,
        actor=actor,
        tier2_assignee_id=body.tier2_assignee_id,
        reason=body.reason,
    )
    database.commit()
    return _respond(
        database,
        ticket_id=ticket_id,
        actor=actor,
        action=AvailableAction.ESCALATE,
        event_id=outcome.event_id,
    )
