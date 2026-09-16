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
    ResolveRequest,
    ResumeRequest,
    TicketActionData,
    TicketActionResponse,
    VendorResponseView,
)
from app.domains.workflow.serializer import ActorContext
from app.domains.workflow.service import (
    EscalateTicketService,
    RequestUserInfoService,
    ResumeTicketService,
    StartTicketService,
    SubmitResolutionService,
)
from app.domains.workflow.ticket_detail import assemble_ticket_detail

router = APIRouter(tags=["Workflow"])


def error_responses(*status_codes: int) -> dict[int, dict[str, object]]:
    return {code: {"model": ErrorResponse} for code in status_codes}


def build_ticket_action_response(
    database: Session,
    *,
    ticket_id: int,
    actor: RequestContext,
    action: AvailableAction,
    event_id: int,
    comment_id: int | None = None,
    vendor_response: VendorResponseView | None = None,
) -> TicketActionResponse:
    """Shared response assembly for every write-path action -- used by this
    router and by ``vendor_workflow.router`` (C029 onward), since both
    domains' actions return the same ``TicketActionResponse`` contract.
    Builds the fresh, post-write TicketDetail (same read C021's
    WorkflowReadModel powers API-17 with) and wraps it in a
    TicketActionData.

    ``comment_id`` defaults to None -- only actions that also write a
    comment (Request User Info, Resume) pass their outcome's comment_id
    through; every other action leaves it unset exactly as before.

    ``vendor_request`` (top-level, on ``TicketActionData``) was previously
    hardcoded to ``None`` for every action. Comparing API26Success/
    API27Success against API28-31Success in docs/api/openapi.yaml shows
    this field should always MIRROR the freshly-assembled
    ``TicketDetail.vendor_request`` -- not stay permanently unset -- so
    C029 fixes that here rather than repeating the old bug in a new
    vendor_workflow-local copy of this helper. ``vendor_response`` has no
    equivalent on ``TicketDetail`` (Vendor Response, C030, is the only
    action that produces one), so it stays an explicit optional param.
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
            vendor_request=ticket.vendor_request,
            vendor_response=vendor_response,
        )
    )


# Backward-compatible alias: this router's own call sites below were
# written against the old private name before the C029 rename. Keeping
# both names avoids a purely-cosmetic diff across every existing call
# site in this same commit; new code (vendor_workflow.router onward)
# should import ``build_ticket_action_response`` directly.
_respond = build_ticket_action_response


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


@router.post(
    "/tickets/{id}/resolve",
    response_model=TicketActionResponse,
    operation_id="api28ResolveTicket",
    summary="Submit resolution",
    tags=["Resolution"],
    responses=error_responses(401, 403, 404, 409, 422, 503),
)
def resolve_ticket(
    ticket_id: Annotated[int, Path(alias="id", ge=1)],
    body: ResolveRequest,
    actor: Annotated[RequestContext, Depends(get_current_actor)],
    database: Annotated[Session, Depends(get_db)],
    _request_id: Annotated[UUID | None, Depends(request_id_header)],
) -> TicketActionResponse:
    outcome = SubmitResolutionService(database).submit_resolution(
        ticket_id=ticket_id, actor=actor, resolution_summary=body.resolution_summary
    )
    database.commit()
    return build_ticket_action_response(
        database,
        ticket_id=ticket_id,
        actor=actor,
        action=AvailableAction.RESOLVE,
        event_id=outcome.event_id,
    )
