"""API-12 and API-14 response schemas."""

from pydantic import BaseModel

from app.common.pagination import PaginationMeta
from app.core.enums import (
    AttachmentVisibility,
    Category,
    CommentVisibility,
    Priority,
    TicketStatus,
)


class AttachmentTypeRule(BaseModel):
    extension: str
    content_type: str


class AttachmentConfig(BaseModel):
    max_size_bytes: int
    upload_url_ttl_seconds: int
    download_url_ttl_seconds: int
    allowed_types: list[AttachmentTypeRule]


class TimerConfig(BaseModel):
    engineering_sla_hours: int
    at_risk_percent: int
    user_response_hours: int
    resolved_window_hours: int


class ReferenceData(BaseModel):
    categories: list[Category]
    priorities: list[Priority]
    ticket_statuses: list[TicketStatus]
    comment_visibilities: list[CommentVisibility]
    attachment_visibilities: list[AttachmentVisibility]
    attachment: AttachmentConfig
    timers: TimerConfig


class ReferenceDataResponse(BaseModel):
    data: ReferenceData


class VendorOrganisation(BaseModel):
    vendor_org_id: int
    name: str
    is_active: bool


class VendorListResponse(BaseModel):
    data: list[VendorOrganisation]
    meta: PaginationMeta
