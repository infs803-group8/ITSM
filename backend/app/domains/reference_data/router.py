"""API-12 and API-14 routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_actor, get_db
from app.common.request_context import RequestContext
from app.common.responses import ErrorResponse
from app.domains.reference_data.schema import ReferenceDataResponse, VendorListResponse
from app.domains.reference_data.service import ReferenceDataService

router = APIRouter(tags=["Reference"])


@router.get(
    "/reference-data",
    response_model=ReferenceDataResponse,
    operation_id="api12ReferenceData",
    responses={401: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
def reference_data(
    actor: Annotated[RequestContext, Depends(get_current_actor)],
    database: Annotated[Session, Depends(get_db)],
) -> ReferenceDataResponse:
    return ReferenceDataService(database).get_reference_data(actor)


@router.get(
    "/vendors",
    response_model=VendorListResponse,
    operation_id="api14ListVendors",
    tags=["Directory"],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
def list_vendors(
    actor: Annotated[RequestContext, Depends(get_current_actor)],
    database: Annotated[Session, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str | None, Query(max_length=100)] = None,
    is_active: bool | None = None,
) -> VendorListResponse:
    return ReferenceDataService(database).list_vendors(
        actor,
        page=page,
        page_size=page_size,
        search=search,
        is_active=is_active,
    )
