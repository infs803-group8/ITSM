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
from app.core.errors import ApplicationError
from app.domains.tickets.detail_assembler import assemble_ticket_detail
from app.domains.workflow.schema import (
    AvailableAction,
    CloseRequest,
    EscalateRequest,
    ReopenRequest,
    RequestUserInfoRequest,
    ResolveRequest,
    ResumeRequest,
    TicketActionData,
    TicketActionResponse,
    VendorResponseView,
)
from app.domains.workflow.service import (
    ConfirmResolutionService,
    EscalateTicketService,
    ManualCloseService,
    ReopenTicketService,
    RequestUserInfoService,
    ResumeTicketService,
    StartTicketService,
    SubmitResolutionService,
)

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
    visibility_already_authorized: bool = False,
) -> TicketActionResponse:
    """Shared response assembly for every write-path action -- used by this
    router and by ``vendor_workflow.router`` (C029 onward), since both
    domains' actions return the same ``TicketActionResponse`` contract.
    Builds the fresh, post-write TicketDetail with Member B's shared
    ``tickets.detail_assembler`` -- the exact assembler GET detail (API-17)
    uses, so an action response and a subsequent GET agree on every field,
    including ``available_actions`` and UTC timestamps -- and wraps it in a
    TicketActionData. The assembler never commits; callers commit the
    action first.

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

    ``visibility_already_authorized`` is passed through to the assembler
    and must stay ``False`` except for ESCALATE, whose Tier 1 caller loses
    normal GET scope the moment the ticket moves to Tier 2 (agreed with B).
    """
    ticket = assemble_ticket_detail(
        database,
        actor=actor,
        ticket_id=ticket_id,
        visibility_already_authorized=visibility_already_authorized,
    )
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
        # The Tier 1 caller was authorised before the write but is no longer
        # the assignee, so the normal GET scope would 404 on a saved action.
        visibility_already_authorized=True,
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


@router.post(
    "/tickets/{id}/confirm-resolution",
    response_model=TicketActionResponse,
    operation_id="api29ConfirmResolution",
    summary="Confirm resolution",
    tags=["Resolution"],
    responses=error_responses(401, 403, 404, 409, 503),
)
def confirm_resolution(
    ticket_id: Annotated[int, Path(alias="id", ge=1)],
    actor: Annotated[RequestContext, Depends(get_current_actor)],
    database: Annotated[Session, Depends(get_db)],
    _request_id: Annotated[UUID | None, Depends(request_id_header)],
) -> TicketActionResponse:
    outcome = ConfirmResolutionService(database).confirm_resolution(
        ticket_id=ticket_id, actor=actor
    )
    database.commit()
    return build_ticket_action_response(
        database,
        ticket_id=ticket_id,
        actor=actor,
        action=AvailableAction.CONFIRM_RESOLUTION,
        event_id=outcome.event_id,
    )


@router.post(
    "/tickets/{id}/reopen",
    response_model=TicketActionResponse,
    operation_id="api30ReopenTicket",
    summary="Reopen ticket",
    tags=["Resolution"],
    responses=error_responses(401, 403, 404, 409, 422, 503),
)
def reopen_ticket(
    ticket_id: Annotated[int, Path(alias="id", ge=1)],
    body: ReopenRequest,
    actor: Annotated[RequestContext, Depends(get_current_actor)],
    database: Annotated[Session, Depends(get_db)],
    _request_id: Annotated[UUID | None, Depends(request_id_header)],
) -> TicketActionResponse:
    outcome = ReopenTicketService(database).reopen(
        ticket_id=ticket_id, actor=actor, reason=body.reason
    )
    database.commit()
    return build_ticket_action_response(
        database,
        ticket_id=ticket_id,
        actor=actor,
        action=AvailableAction.REOPEN,
        event_id=outcome.event_id,
        comment_id=outcome.comment_id,
    )


@router.post(
    "/tickets/{id}/close",
    response_model=TicketActionResponse,
    operation_id="api31CloseTicket",
    summary="Manual close",
    tags=["Resolution"],
    responses=error_responses(401, 403, 404, 409, 422, 503),
)
def close_ticket(
    ticket_id: Annotated[int, Path(alias="id", ge=1)],
    body: CloseRequest,
    actor: Annotated[RequestContext, Depends(get_current_actor)],
    database: Annotated[Session, Depends(get_db)],
    _request_id: Annotated[UUID | None, Depends(request_id_header)],
) -> TicketActionResponse:
    outcome = ManualCloseService(database).manual_close(
        ticket_id=ticket_id, actor=actor, reason=body.reason
    )
    database.commit()
    return build_ticket_action_response(
        database,
        ticket_id=ticket_id,
        actor=actor,
        action=AvailableAction.CLOSE,
        event_id=outcome.event_id,
    )
