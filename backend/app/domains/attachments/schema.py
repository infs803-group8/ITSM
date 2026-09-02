"""Pydantic contract for Member A attachment API-02 through API-05."""

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

from app.common.pagination import PaginationMeta
from app.core.enums import AttachmentVisibility

MAX_ATTACHMENT_BYTES = 10_485_760


class AttachmentContentType(StrEnum):
    PNG = "image/png"
    JPEG = "image/jpeg"
    PDF = "application/pdf"
    TEXT = "text/plain"


class PresignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_name: str = Field(min_length=1, max_length=255)
    content_type: AttachmentContentType
    size_bytes: int = Field(ge=1, le=MAX_ATTACHMENT_BYTES)
    visibility: AttachmentVisibility


class PresignData(BaseModel):
    upload_id: UUID
    upload_url: AnyHttpUrl
    method: Literal["PUT"] = "PUT"
    signed_headers: dict[str, str]
    expires_at: datetime
    max_size_bytes: Literal[10_485_760] = MAX_ATTACHMENT_BYTES


class PresignResponse(BaseModel):
    data: PresignData


class CompleteUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upload_id: UUID


class AttachmentData(BaseModel):
    attachment_id: UUID
    ticket_id: int
    file_name: str = Field(min_length=1, max_length=255)
    content_type: AttachmentContentType
    size_bytes: int = Field(ge=1, le=MAX_ATTACHMENT_BYTES)
    visibility: AttachmentVisibility
    created_at: datetime


class AttachmentResponse(BaseModel):
    data: AttachmentData


class AttachmentListResponse(BaseModel):
    data: list[AttachmentData]
    meta: PaginationMeta


class DownloadData(BaseModel):
    attachment_id: UUID
    file_name: str
    content_type: str
    download_url: AnyHttpUrl
    expires_at: datetime


class DownloadResponse(BaseModel):
    data: DownloadData
