"""vendor_workflow API routes (C029 onward).

Implemented exactly as backend/contracts/openapi.yaml specifies per operation.
Reuses ``workflow.router``'s ``error_responses``/``build_ticket_action_response``
helpers rather than duplicating them -- this domain's actions still return
the same shared ``TicketActionResponse`` contract every C024-C034 write-path
action does.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_actor, get_db, request_id_header
from app.common.request_context import RequestContext
from app.domains.tickets.schema import VendorResponseView
from app.domains.vendor_workflow.schema import VendorRequestCreate, VendorResponseRequest
from app.domains.vendor_workflow.service import RequestVendorService, VendorResponseService
from app.domains.workflow.router import build_ticket_action_response, error_responses
from app.domains.workflow.schema import AvailableAction, TicketActionResponse

router = APIRouter(tags=["Vendor Workflow"])


@router.post(
    "/tickets/{id}/vendor-requests",
    response_model=TicketActionResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="api26CreateVendorRequest",
    summary="Request vendor",
    responses=error_responses(401, 403, 404, 409, 422, 503),
)
def create_vendor_request(
    ticket_id: Annotated[int, Path(alias="id", ge=1)],
    body: VendorRequestCreate,
    actor: Annotated[RequestContext, Depends(get_current_actor)],
    database: Annotated[Session, Depends(get_db)],
    _request_id: Annotated[UUID | None, Depends(request_id_header)],
) -> TicketActionResponse:
    outcome = RequestVendorService(database).request_vendor(
        ticket_id=ticket_id,
        actor=actor,
        vendor_org_id=body.vendor_org_id,
        vendor_message=body.vendor_message,
    )
    database.commit()
    return build_ticket_action_response(
        database,
        ticket_id=ticket_id,
        actor=actor,
        action=AvailableAction.REQUEST_VENDOR,
        event_id=outcome.event_id,
    )


@router.post(
    "/tickets/{id}/vendor-response",
    response_model=TicketActionResponse,
    operation_id="api27VendorResponse",
    summary="Vendor response",
    responses=error_responses(401, 403, 404, 409, 422, 503),
)
def submit_vendor_response(
    ticket_id: Annotated[int, Path(alias="id", ge=1)],
    body: VendorResponseRequest,
    actor: Annotated[RequestContext, Depends(get_current_actor)],
    database: Annotated[Session, Depends(get_db)],
    _request_id: Annotated[UUID | None, Depends(request_id_header)],
) -> TicketActionResponse:
    outcome = VendorResponseService(database).respond(
        ticket_id=ticket_id, actor=actor, message=body.message
    )
    database.commit()
    vendor_response = VendorResponseView(
        vendor_response_id=outcome.vendor_response_id,
        vendor_request_id=outcome.vendor_request_id,
        message=outcome.message,
        created_at=outcome.created_at,
    )
    return build_ticket_action_response(
        database,
        ticket_id=ticket_id,
        actor=actor,
        action=AvailableAction.VENDOR_RESPONSE,
        event_id=outcome.event_id,
        vendor_response=vendor_response,
    )
