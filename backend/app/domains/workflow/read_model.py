"""Concrete ``WorkflowReadModel`` implementation (C021).

``app.contracts.workflow_read_model.WorkflowReadModel`` is a narrow Protocol
-- ``get_ticket_workflow(*, ticket_id) -> dict`` -- with no actor parameter,
so it can only hand back the objective, role-agnostic workflow snapshot for
a ticket. Role-aware serialization needs an actor, so it lives on this
concrete class as an additional method (``get_role_view``) rather than on
the Protocol; callers that only have a ticket_id (e.g. another domain that
just needs to know the current SLA cycle) use ``get_ticket_workflow``,
while the tickets/comments HTTP layer building an actual API response uses
``get_role_view``.
"""

from typing import Any

from sqlalchemy.orm import Session

from app.core.clock import as_utc
from app.domains.workflow.repository import WorkflowRepository
from app.domains.workflow.serializer import ActorContext, build_ticket_workflow_view


class WorkflowReadModel:
    """Implements ``app.contracts.workflow_read_model.WorkflowReadModel``."""

    def __init__(self, database: Session) -> None:
        self.database = database
        self.repository = WorkflowRepository(database)

    def get_ticket_workflow(self, *, ticket_id: int) -> dict[str, Any]:
        """Objective (non-role-filtered) workflow snapshot for this ticket.

        Raises ``KeyError`` if the ticket does not exist -- callers that
        need 404-shaped handling (the HTTP layer) already resolve ticket
        existence earlier via B's tickets domain before reaching here, so
        this stays a plain, un-wrapped lookup rather than importing
        ``ApplicationError`` into a module other domains depend on.
        """
        raw = self.repository.get_workflow_snapshot(ticket_id)
        if raw is None:
            raise KeyError(f"ticket {ticket_id} not found")
        vendor_row = self.repository.get_latest_vendor_request(ticket_id)
        return {
            "ticket_id": raw["ticket_id"],
            "status": raw["status_code"],
            "requester_id": raw["requester_id"],
            "assignee_id": raw["assignee_id"],
            "sla_cycle_no": raw["sla_cycle_no"],
            "sla_status": raw["sla_status_code"],
            "sla_started_at": _isoformat(raw.get("sla_started_at")),
            "sla_deadline": _isoformat(raw.get("sla_deadline")),
            "pending_user_reason": raw.get("pending_user_reason"),
            "pending_user_deadline": _isoformat(raw.get("pending_user_deadline")),
            "resolution_summary": raw.get("resolution_summary"),
            "resolution_type": raw.get("resolution_type"),
            "resolved_at": _isoformat(raw.get("resolved_at")),
            "auto_close_at": _isoformat(raw.get("auto_close_at")),
            "closure_type": raw.get("closure_type"),
            "closed_at": _isoformat(raw.get("closed_at")),
            "has_active_vendor_request": bool(
                vendor_row is not None and vendor_row["status"] == "ACTIVE"
            ),
            "active_vendor_org_id": (
                vendor_row["vendor_org_id"]
                if vendor_row is not None and vendor_row["status"] == "ACTIVE"
                else None
            ),
        }

    def get_role_view(self, *, ticket_id: int, actor: ActorContext) -> dict[str, Any]:
        """The role-serialized workflow slice of ``TicketDetail``/
        ``TicketSummary`` (C021.01/.02/.03/.04) -- see
        ``app.domains.workflow.serializer`` for exactly what this does and
        does not cover.
        """
        raw = self.repository.get_workflow_snapshot(ticket_id)
        if raw is None:
            raise KeyError(f"ticket {ticket_id} not found")
        raw = dict(raw)
        for key in ("sla_started_at", "sla_deadline", "pending_user_deadline", "resolved_at", "auto_close_at", "closed_at"):
            raw[key] = _isoformat(raw.get(key))
        vendor_row = self.repository.get_latest_vendor_request(ticket_id)
        if vendor_row is not None:
            vendor_row = dict(vendor_row)
            vendor_row["created_at"] = _isoformat(vendor_row.get("created_at"))
            vendor_row["responded_at"] = _isoformat(vendor_row.get("responded_at"))
        return build_ticket_workflow_view(raw, vendor_row, actor=actor)


def _isoformat(value: Any) -> str | None:
    """MySQL DATETIME columns come back as naive ``datetime`` via PyMySQL;
    treat them as UTC (same convention as every other C repository) and
    render as an aware ISO-8601 string for the API response.
    """
    if value is None:
        return None
    return as_utc(value).isoformat()
