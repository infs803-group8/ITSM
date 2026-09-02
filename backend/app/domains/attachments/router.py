"""API-02 through API-05 attachment routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_actor, get_db, request_id_header
from app.common.request_context import RequestContext
from app.common.responses import ErrorResponse
from app.core.enums import AttachmentVisibility
from app.core.errors import ApplicationError
from app.domains.attachments.schema import (
    AttachmentListResponse,
    AttachmentResponse,
    CompleteUploadRequest,
    DownloadResponse,
    PresignRequest,
    PresignResponse,
)
from app.domains.attachments.service import AttachmentService
from app.integrations.s3.object_verification import ObjectStorageError
from app.integrations.s3.presigned_urls import ObjectStorage, S3ObjectStorage

router = APIRouter(tags=["Attachments"])


def get_object_storage() -> ObjectStorage:
    try:
        return S3ObjectStorage()
    except ObjectStorageError:
        raise ApplicationError(
            "STORAGE_UNAVAILABLE",
            "Object storage is not configured or temporarily unavailable.",
            503,
        ) from None


def error_responses(*status_codes: int) -> dict[int, dict[str, object]]:
    return {code: {"model": ErrorResponse} for code in status_codes}


@router.post(
    "/tickets/{id}/attachments/presign",
    response_model=PresignResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="api02CreateAttachmentUpload",
    summary="Create attachment upload session",
    responses=error_responses(401, 403, 404, 409, 413, 422, 503),
)
def create_attachment_upload(
    ticket_id: Annotated[int, Path(alias="id", ge=1)],
    body: PresignRequest,
    actor: Annotated[RequestContext, Depends(get_current_actor)],
    database: Annotated[Session, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    _request_id: Annotated[UUID | None, Depends(request_id_header)],
) -> PresignResponse:
    return AttachmentService(database, storage).create_upload_session(ticket_id, actor, body)


@router.post(
    "/tickets/{id}/attachments/complete",
    response_model=AttachmentResponse,
    operation_id="api03CompleteAttachmentUpload",
    summary="Complete attachment upload",
    responses=error_responses(401, 404, 409, 422, 503),
)
def complete_attachment_upload(
    ticket_id: Annotated[int, Path(alias="id", ge=1)],
    body: CompleteUploadRequest,
    actor: Annotated[RequestContext, Depends(get_current_actor)],
    database: Annotated[Session, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    _request_id: Annotated[UUID | None, Depends(request_id_header)],
) -> AttachmentResponse:
    return AttachmentService(database, storage).complete_upload(ticket_id, actor, body)


@router.get(
    "/tickets/{id}/attachments",
    response_model=AttachmentListResponse,
    operation_id="api04ListAttachments",
    summary="List ticket attachments",
    responses=error_responses(401, 403, 404, 422, 503),
)
def list_attachments(
    ticket_id: Annotated[int, Path(alias="id", ge=1)],
    actor: Annotated[RequestContext, Depends(get_current_actor)],
    database: Annotated[Session, Depends(get_db)],
    _request_id: Annotated[UUID | None, Depends(request_id_header)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    visibility: Annotated[AttachmentVisibility | None, Query()] = None,
) -> AttachmentListResponse:
    return AttachmentService(database, None).list_attachments(
        ticket_id,
        actor,
        page=page,
        page_size=page_size,
        visibility=visibility,
    )


@router.get(
    "/tickets/{id}/attachments/{attachment_id}/download",
    response_model=DownloadResponse,
    operation_id="api05GetAttachmentDownload",
    summary="Generate attachment download URL",
    responses=error_responses(401, 404, 503),
)
def get_attachment_download(
    ticket_id: Annotated[int, Path(alias="id", ge=1)],
    attachment_id: UUID,
    actor: Annotated[RequestContext, Depends(get_current_actor)],
    database: Annotated[Session, Depends(get_db)],
    storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    _request_id: Annotated[UUID | None, Depends(request_id_header)],
) -> DownloadResponse:
    return AttachmentService(database, storage).create_download(
        ticket_id, attachment_id, actor
    )
