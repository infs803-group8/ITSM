"""API-15 through API-18 routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_actor, get_db
from app.common.request_context import RequestContext
from app.common.responses import ErrorResponse
from app.core.enums import Category, Priority, SlaStatus, TicketStatus
from app.domains.tickets.schema import (
    SortOrder,
    TicketCreateRequest,
    TicketDetailResponse,
    TicketListResponse,
    TicketSortBy,
    TicketUpdateRequest,
)
from app.domains.tickets.service import TicketService

router = APIRouter(prefix="/tickets", tags=["Tickets"])


@router.post(
    "",
    response_model=TicketDetailResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="api15CreateTicket",
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
def create_ticket(
    request: TicketCreateRequest,
    actor: Annotated[RequestContext, Depends(get_current_actor)],
    database: Annotated[Session, Depends(get_db)],
) -> TicketDetailResponse:
    return TicketService(database).create(actor, request)


@router.get(
    "",
    response_model=TicketListResponse,
    operation_id="api16ListTickets",
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
def list_tickets(
    actor: Annotated[RequestContext, Depends(get_current_actor)],
    database: Annotated[Session, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    status_filter: Annotated[TicketStatus | None, Query(alias="status")] = None,
    category: Category | None = None,
    priority: Priority | None = None,
    sla_status: SlaStatus | None = None,
    assignee_id: Annotated[int | None, Query(ge=1)] = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    sort_by: TicketSortBy = TicketSortBy.CREATED_AT,
    sort_order: SortOrder = SortOrder.DESC,
) -> TicketListResponse:
    return TicketService(database).list(
        actor,
        page=page,
        page_size=page_size,
        status=status_filter,
        category=category,
        priority=priority,
        sla_status=sla_status,
        assignee_id=assignee_id,
        search=search,
        sort_by=sort_by.value,
        sort_order=sort_order.value,
    )


@router.get(
    "/{id}",
    response_model=TicketDetailResponse,
    operation_id="api17GetTicket",
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def get_ticket(
    id: Annotated[int, Path(ge=1)],
    actor: Annotated[RequestContext, Depends(get_current_actor)],
    database: Annotated[Session, Depends(get_db)],
) -> TicketDetailResponse:
    return TicketService(database).get(actor, id)


@router.patch(
    "/{id}",
    response_model=TicketDetailResponse,
    operation_id="api18UpdateTicket",
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def update_ticket(
    request: TicketUpdateRequest,
    id: Annotated[int, Path(ge=1)],
    actor: Annotated[RequestContext, Depends(get_current_actor)],
    database: Annotated[Session, Depends(get_db)],
) -> TicketDetailResponse:
    return TicketService(database).update(actor, id, request)
