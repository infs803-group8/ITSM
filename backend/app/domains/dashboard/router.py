"""API-06 and API-07 dashboard routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_actor, get_db, request_id_header
from app.common.request_context import RequestContext
from app.common.responses import ErrorResponse
from app.core.enums import Category, Priority
from app.domains.dashboard.schema import (
    DashboardSummaryResponse,
    OverdueListResponse,
    OverdueMode,
)
from app.domains.dashboard.service import DashboardService

router = APIRouter(tags=["Dashboard"])


def error_responses(*status_codes: int) -> dict[int, dict[str, object]]:
    return {code: {"model": ErrorResponse} for code in status_codes}


@router.get(
    "/dashboard/summary",
    response_model=DashboardSummaryResponse,
    operation_id="api06DashboardSummary",
    summary="Get dashboard summary",
    responses=error_responses(401, 403, 503),
)
def dashboard_summary(
    actor: Annotated[RequestContext, Depends(get_current_actor)],
    database: Annotated[Session, Depends(get_db)],
    _request_id: Annotated[UUID | None, Depends(request_id_header)],
) -> DashboardSummaryResponse:
    return DashboardService(database).summary(actor)


@router.get(
    "/dashboard/overdue-tickets",
    response_model=OverdueListResponse,
    operation_id="api07OverdueTickets",
    summary="List current/history overdue",
    responses=error_responses(401, 403, 422, 503),
)
def overdue_tickets(
    actor: Annotated[RequestContext, Depends(get_current_actor)],
    database: Annotated[Session, Depends(get_db)],
    _request_id: Annotated[UUID | None, Depends(request_id_header)],
    mode: Annotated[OverdueMode, Query()] = OverdueMode.CURRENT,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    category: Annotated[Category | None, Query()] = None,
    priority: Annotated[Priority | None, Query()] = None,
) -> OverdueListResponse:
    return DashboardService(database).overdue(
        actor,
        mode=mode,
        page=page,
        page_size=page_size,
        category=category,
        priority=priority,
    )
