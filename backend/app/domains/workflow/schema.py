"""Pydantic contract for the write-path ``TicketActionResponse`` shape
shared by every C024-C034 endpoint, plus the request bodies for the
workflow actions those endpoints accept.

Field shapes are copied 1:1 from docs/api/openapi.yaml's
``TicketDetail``/``TicketActionData``/``TicketActionResponse`` and the
per-action ``*Request`` schemas. ``TicketDetail`` is nominally Member B's
schema (``app.domains.tickets.*`` is still an empty stub), defined here as
a stopgap so C024-C034 can return a complete, schema-correct response
today -- see ``workflow/ticket_detail.py``'s docstring for the same
reasoning applied to assembling its data. Once B builds their own
``tickets/schema.py``, these models should move there and every import
here should be repointed, since B, not C, owns that shape long-term.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.enums import Category, Priority, TicketStatus


class AvailableAction(StrEnum):
    """docs/api/openapi.yaml: AvailableAction. 11 of these 14 members are
    workflow actions (see ``serializer._PUBLIC_ACTION_LABELS``); EDIT,
    COMMENT and UPLOAD_ATTACHMENT belong to other domains.
    """

    EDIT = "EDIT"
    COMMENT = "COMMENT"
    UPLOAD_ATTACHMENT = "UPLOAD_ATTACHMENT"
    ASSIGN = "ASSIGN"
    START = "START"
    REQUEST_USER_INFO = "REQUEST_USER_INFO"
    RESUME = "RESUME"
    ESCALATE = "ESCALATE"
    REQUEST_VENDOR = "REQUEST_VENDOR"
    VENDOR_RESPONSE = "VENDOR_RESPONSE"
    RESOLVE = "RESOLVE"
    CONFIRM_RESOLUTION = "CONFIRM_RESOLUTION"
    REOPEN = "REOPEN"
    CLOSE = "CLOSE"


class RequesterSummary(BaseModel):
    user_id: int
    display_name: str


class AssigneeSummary(BaseModel):
    user_id: int
    display_name: str
    tier: str
    skills: list[Category]
    is_available: bool
    active_load: int = Field(ge=0)


class SlaView(BaseModel):
    cycle_no: int = Field(ge=1)
    status: str
    started_at: datetime | None
    deadline: datetime | None


class PendingUserView(BaseModel):
    reason: str
    deadline: datetime


class ResolutionView(BaseModel):
    summary: str
    type: str | None
    resolved_at: datetime | None
    auto_close_at: datetime | None


class ClosureView(BaseModel):
    type: str
    closed_at: datetime


class VendorOrganisationView(BaseModel):
    vendor_org_id: int
    name: str
    is_active: bool


class VendorRequestView(BaseModel):
    vendor_request_id: int
    vendor_org: VendorOrganisationView
    status: str
    vendor_message: str
    created_at: datetime
    responded_at: datetime | None


class VendorResponseView(BaseModel):
    vendor_response_id: int
    vendor_request_id: int
    message: str
    created_at: datetime


class TicketDetail(BaseModel):
    """docs/api/openapi.yaml: TicketDetail. Required keys are stable;
    role-unavailable values are JSON null (enforced by
    ``workflow/ticket_detail.assemble_ticket_detail``, not by this model).
    """

    ticket_id: int
    title: str
    description: str | None
    category: Category
    priority: Priority
    status: TicketStatus
    display_status: str
    requester: RequesterSummary | None
    assignee: AssigneeSummary | None
    sla: SlaView | None
    pending_user: PendingUserView | None
    resolution: ResolutionView | None
    closure: ClosureView | None
    vendor_request: VendorRequestView | None
    available_actions: list[AvailableAction]
    created_at: datetime
    updated_at: datetime


class TicketActionData(BaseModel):
    action: AvailableAction
    ticket: TicketDetail
    event_id: int
    comment_id: int | None
    vendor_request: VendorRequestView | None
    vendor_response: VendorResponseView | None


class TicketActionResponse(BaseModel):
    data: TicketActionData


class RequestUserInfoRequest(BaseModel):
    """docs/api/openapi.yaml: RequestUserInfoRequest (API-23)."""

    message: str = Field(min_length=1, max_length=4000)

    model_config = {"extra": "forbid"}


class ResumeRequest(BaseModel):
    """docs/api/openapi.yaml: ResumeRequest (API-24). Covers both Resume
    (from INFORMATION_REQUIRED) and Issue Persists (from
    RESOLUTION_CONFIRMATION) -- one request shape for the one endpoint,
    same as ``state_machine.WorkflowAction.USER_RESUME``.
    """

    message: str = Field(min_length=1, max_length=4000)

    model_config = {"extra": "forbid"}


class EscalateRequest(BaseModel):
    """docs/api/openapi.yaml: EscalateRequest (API-25)."""

    tier2_assignee_id: int
    reason: str | None = Field(default=None, min_length=1, max_length=1000)

    model_config = {"extra": "forbid"}


class ResolveRequest(BaseModel):
    """docs/api/openapi.yaml: ResolveRequest (API-28)."""

    resolution_summary: str = Field(min_length=1, max_length=5000)

    model_config = {"extra": "forbid"}


class ReopenRequest(BaseModel):
    """docs/api/openapi.yaml: ReopenRequest (API-30)."""

    reason: str = Field(min_length=1, max_length=4000)

    model_config = {"extra": "forbid"}


class CloseRequest(BaseModel):
    """docs/api/openapi.yaml: CloseRequest (API-31). ``acknowledge`` is
    typed ``Literal[True]`` rather than ``bool`` -- pydantic then rejects
    ``false`` (or any non-bool) at validation time on its own, matching
    the schema's own ``"const": true``, with no extra check needed here.
    """

    acknowledge: Literal[True]
    reason: str | None = Field(default=None, min_length=1, max_length=1000)

    model_config = {"extra": "forbid"}


class AssignmentRequest(BaseModel):
    """docs/api/openapi.yaml: AssignmentRequest (API-21)."""

    assignee_id: int
    reason: str | None = Field(default=None, min_length=1, max_length=1000)

    model_config = {"extra": "forbid"}
