"""API-15 through API-18 request and response schemas."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.common.pagination import PaginationMeta
from app.core.clock import as_utc
from app.core.enums import (
    AvailableAction,
    Category,
    PendingUserReason,
    Priority,
    SlaStatus,
    TicketStatus,
    VendorRequestStatus,
)
from app.domains.reference_data.schema import VendorOrganisation
from app.domains.users.schema import AssigneeSummary


class TicketSortBy(StrEnum):
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    SLA_DEADLINE = "sla_deadline"
    PRIORITY = "priority"


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


class TicketCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=5000)
    category: Category
    priority: Priority

    @field_validator("title", "description")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value


class TicketUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=5000)
    category: Category | None = None
    priority: Priority | None = None

    @field_validator("title", "description")
    @classmethod
    def text_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("value must not be blank")
        return value

    @model_validator(mode="after")
    def require_fields(self) -> "TicketUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("At least one ticket field must be provided.")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Ticket fields cannot be null.")
        return self


class RequesterSummary(BaseModel):
    user_id: int
    display_name: str


class SlaView(BaseModel):
    cycle_no: int = Field(ge=1)
    status: SlaStatus
    started_at: datetime | None
    deadline: datetime | None

    @field_validator("started_at", "deadline", mode="after")
    @classmethod
    def datetimes_are_utc(cls, value: datetime | None) -> datetime | None:
        return as_utc(value) if value is not None else None


class PendingUserView(BaseModel):
    reason: PendingUserReason
    deadline: datetime

    @field_validator("deadline", mode="after")
    @classmethod
    def deadline_is_utc(cls, value: datetime) -> datetime:
        return as_utc(value)


class ResolutionView(BaseModel):
    summary: str = Field(min_length=1, max_length=5000)
    type: str | None
    resolved_at: datetime | None
    auto_close_at: datetime | None

    @field_validator("resolved_at", "auto_close_at", mode="after")
    @classmethod
    def datetimes_are_utc(cls, value: datetime | None) -> datetime | None:
        return as_utc(value) if value is not None else None


class ClosureView(BaseModel):
    type: str
    closed_at: datetime

    @field_validator("closed_at", mode="after")
    @classmethod
    def closed_at_is_utc(cls, value: datetime) -> datetime:
        return as_utc(value)


class VendorRequestView(BaseModel):
    vendor_request_id: int
    vendor_org: VendorOrganisation
    status: VendorRequestStatus
    vendor_message: str = Field(max_length=4000)
    created_at: datetime
    responded_at: datetime | None

    @field_validator("created_at", "responded_at", mode="after")
    @classmethod
    def datetimes_are_utc(cls, value: datetime | None) -> datetime | None:
        return as_utc(value) if value is not None else None


class VendorResponseView(BaseModel):
    vendor_response_id: int
    vendor_request_id: int
    message: str = Field(max_length=4000)
    created_at: datetime

    @field_validator("created_at", mode="after")
    @classmethod
    def created_at_is_utc(cls, value: datetime) -> datetime:
        return as_utc(value)


class VendorRequestHistoryView(VendorRequestView):
    response: VendorResponseView | None


class VendorRequestHistoryResponse(BaseModel):
    data: list[VendorRequestHistoryView]


class TicketSummary(BaseModel):
    ticket_id: int
    title: str
    category: Category
    priority: Priority
    status: TicketStatus
    display_status: str
    assignee: AssigneeSummary | None
    sla: SlaView | None
    available_actions: list[AvailableAction]
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at", mode="after")
    @classmethod
    def datetimes_are_utc(cls, value: datetime) -> datetime:
        return as_utc(value)


class TicketDetail(TicketSummary):
    description: str | None
    requester: RequesterSummary | None
    pending_user: PendingUserView | None
    resolution: ResolutionView | None
    closure: ClosureView | None
    vendor_request: VendorRequestView | None


class TicketDetailResponse(BaseModel):
    data: TicketDetail


class TicketListResponse(BaseModel):
    data: list[TicketSummary]
    meta: PaginationMeta
