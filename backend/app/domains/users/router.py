"""users API routes.

Implement operations exactly from backend/contracts/openapi.yaml.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_actor, get_db
from app.common.request_context import RequestContext
from app.common.responses import ErrorResponse
from app.core.enums import Category
from app.domains.users.schema import AssigneeListResponse, UpdateProfileRequest, UserResponse
from app.domains.users.service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/me",
    response_model=UserResponse,
    operation_id="api10GetMyProfile",
    summary="Get current user profile",
    responses={401: {"model": ErrorResponse}},
)
def get_me(
    actor: Annotated[RequestContext, Depends(get_current_actor)],
    database: Annotated[Session, Depends(get_db)],
) -> UserResponse:
    return UserService(database).get_profile(actor)


@router.patch(
    "/me",
    response_model=UserResponse,
    operation_id="api11UpdateMyProfile",
    summary="Update current user profile",
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
def update_me(
    request: UpdateProfileRequest,
    actor: Annotated[RequestContext, Depends(get_current_actor)],
    database: Annotated[Session, Depends(get_db)],
) -> UserResponse:
    return UserService(database).update_profile(actor, request)


@router.get(
    "/assignees",
    response_model=AssigneeListResponse,
    operation_id="api13ListAssignees",
    tags=["Directory"],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
def list_assignees(
    actor: Annotated[RequestContext, Depends(get_current_actor)],
    database: Annotated[Session, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    tier: Annotated[str | None, Query(pattern="^(TIER1|TIER2)$")] = None,
    category: Category | None = None,
    is_available: bool | None = None,
) -> AssigneeListResponse:
    return UserService(database).list_assignees(
        actor,
        page=page,
        page_size=page_size,
        tier=tier,
        category=category,
        is_available=is_available,
    )
