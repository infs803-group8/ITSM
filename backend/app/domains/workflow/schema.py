"""Pydantic contract for the write-path ``TicketActionResponse`` shape
shared by every C024-C034 endpoint, plus the request bodies for the
workflow actions those endpoints accept.

``TicketDetail`` and its nested views are Member B's schema
(``app.domains.tickets.schema``) and ``AvailableAction`` lives in
``app.core.enums``; both are imported here rather than redefined, so the
ticket inside every action response is the exact model GET detail
(API-17) returns. ``AvailableAction`` is re-exported for existing callers.
``VendorResponseView`` is also a shared ticket-domain model because the
Q03 history read returns it after the original API-27 action response.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.core.enums import AvailableAction
from app.domains.tickets.schema import TicketDetail, VendorRequestView, VendorResponseView

__all__ = [
    "AssignmentRequest",
    "AvailableAction",
    "CloseRequest",
    "EscalateRequest",
    "ReopenRequest",
    "RequestUserInfoRequest",
    "ResolveRequest",
    "ResumeRequest",
    "TicketActionData",
    "TicketActionResponse",
    "VendorResponseView",
]


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
