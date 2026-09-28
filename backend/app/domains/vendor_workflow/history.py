"""Vendor request/response history read (Q03, C047).

C owns the database read and the Vendor organisation isolation for the
``GET /tickets/{id}/vendor-requests`` endpoint; Member B owns the route,
ticket-level access (404 when the ticket is not visible), the public
response model, OpenAPI and cross-domain serialization.

Role rule (agreed with B):
* ENGINEER_TIER2 / SERVICE_DESK_MANAGER: every request on the ticket.
* EXTERNAL_VENDOR: only their own organisation's requests and responses.
  A vendor actor without an organisation gets nothing (fail closed).
* USER / ENGINEER_TIER1: never -- 403 DATA_SCOPE_DENIED.

This module does not check whether the ticket itself is visible to the
actor; the caller (B's route) must do that first, exactly as GET detail
does. Output keys mirror ``tickets.schema.VendorRequestView`` plus a
``response`` object shaped like ``VendorResponseView`` (or ``None``). No
internal-user fields (requester / responder IDs) are exposed. Timestamps
are UTC-aware.
"""

from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from app.common.request_context import RequestContext
from app.core.clock import as_utc
from app.core.enums import UserRole
from app.core.errors import ApplicationError
from app.domains.vendor_workflow.repository import VendorWorkflowRepository

_INTERNAL_READERS = {UserRole.ENGINEER_TIER2, UserRole.SERVICE_DESK_MANAGER}


def _utc(value: Any) -> Any:
    return as_utc(value) if value is not None else None


def serialize_history_row(row: Mapping[str, Any]) -> dict[str, Any]:
    response = None
    if row["vendor_response_id"] is not None:
        response = {
            "vendor_response_id": int(row["vendor_response_id"]),
            "vendor_request_id": int(row["vendor_request_id"]),
            "message": row["response_message"],
            "created_at": _utc(row["response_created_at"]),
        }
    return {
        "vendor_request_id": int(row["vendor_request_id"]),
        "vendor_org": {
            "vendor_org_id": int(row["vendor_org_id"]),
            "name": row["vendor_org_name"],
            "is_active": bool(row["vendor_org_is_active"]),
        },
        "status": row["status"],
        "vendor_message": row["vendor_message"],
        "created_at": _utc(row["created_at"]),
        "responded_at": _utc(row["responded_at"]),
        "response": response,
    }


class VendorHistoryReader:
    def __init__(self, database: Session) -> None:
        self.repository = VendorWorkflowRepository(database)

    def list_for_actor(self, *, ticket_id: int, actor: RequestContext) -> list[dict[str, Any]]:
        role = UserRole(actor.role)
        if role in _INTERNAL_READERS:
            vendor_org_id = None
        elif role is UserRole.EXTERNAL_VENDOR:
            if actor.vendor_org_id is None:
                return []
            vendor_org_id = actor.vendor_org_id
        else:
            raise ApplicationError(
                "DATA_SCOPE_DENIED",
                "Vendor collaboration history is not available to this role.",
                403,
            )
        rows = self.repository.list_request_history(
            ticket_id=ticket_id, vendor_org_id=vendor_org_id
        )
        return [serialize_history_row(row) for row in rows]
