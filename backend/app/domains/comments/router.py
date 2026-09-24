"""API-19 and API-20 routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_actor, get_db
from app.common.request_context import RequestContext
from app.common.responses import ErrorResponse
from app.core.enums import CommentVisibility
from app.domains.comments.schema import (
    CommentCreateRequest,
    CommentListResponse,
    CommentResponse,
)
from app.domains.comments.service import CommentService

router = APIRouter(prefix="/tickets/{id}/comments", tags=["Comments"])


@router.get(
    "",
    response_model=CommentListResponse,
    operation_id="api19ListComments",
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)
def list_comments(
    id: Annotated[int, Path(ge=1)],
    actor: Annotated[RequestContext, Depends(get_current_actor)],
    database: Annotated[Session, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    visibility: CommentVisibility | None = None,
) -> CommentListResponse:
    return CommentService(database).list(
        actor, id, page=page, page_size=page_size, visibility=visibility
    )


@router.post(
    "",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="api20CreateComment",
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def create_comment(
    request: CommentCreateRequest,
    id: Annotated[int, Path(ge=1)],
    actor: Annotated[RequestContext, Depends(get_current_actor)],
    database: Annotated[Session, Depends(get_db)],
) -> CommentResponse:
    return CommentService(database).create(actor, id, request)
