"""Shared execution shape for the write-path workflow actions C025-C034
implement (Start, Request User Info, Resume, Escalate, Request Vendor,
Vendor Response, Submit Resolution, Confirm Resolution, Reopen, Manual
Close). Every one of these actions locks the ticket row, builds a
``TicketState``, calls ``state_machine.evaluate()`` against a concrete
``ActionRequest``, and -- if allowed -- applies whatever write that
action's ``TransitionResult`` implies plus exactly one audit event.
Building the shared lock-and-build-state step once here keeps each
individual action's own service module down to the parts that actually
differ between actions: its own repository write and its own event
metadata.
"""

from dataclasses import dataclass
from datetime import datetime

from app.core.clock import as_utc
from app.core.enums import UserRole
from app.core.errors import ApplicationError
from app.domains.workflow.error_mapping import error_for_denial
from app.domains.workflow.repository import WorkflowRepository
from app.domains.workflow.state_machine import (
    ActionRequest,
    PendingUserReason,
    SlaStatus,
    TicketState,
    TicketStatus,
    TransitionResult,
    evaluate,
)


@dataclass(frozen=True)
class LockedTicket:
    row: dict
    state: TicketState
    active_vendor_org_id: int | None


def lock_ticket_state(
    repository: WorkflowRepository, *, ticket_id: int, now: datetime
) -> LockedTicket:
    """Lock the ticket row and assemble the ``TicketState`` every action
    handler evaluates against. Raises 404 if the ticket does not exist.

    The overdue judgment (shared with C024's ``AssignTicketService``, not
    yet itself deduplicated into one place -- flagged for a future
    cleanup once both call sites exist side by side) uses the real
    deadline rather than only the possibly-lagging stored
    ``sla_status_code``, per the same reasoning as C024.02.
    """
    row = repository.get_ticket_state_row(ticket_id)
    if row is None:
        raise ApplicationError("RESOURCE_NOT_FOUND", "The requested resource was not found.", 404)
    latest_vendor = repository.get_latest_vendor_request(ticket_id)
    active_vendor_org_id = (
        latest_vendor["vendor_org_id"]
        if latest_vendor is not None and latest_vendor["status"] == "ACTIVE"
        else None
    )
    is_overdue_now = row["sla_status_code"] == "OVERDUE" or (
        row["sla_deadline"] is not None and now >= as_utc(row["sla_deadline"])
    )
    sla_status = SlaStatus.OVERDUE if is_overdue_now else SlaStatus(row["sla_status_code"])
    state = TicketState(
        status=TicketStatus(row["status_code"]),
        assignee_id=row["assignee_id"],
        assignee_role=UserRole(row["assignee_role_code"]) if row["assignee_role_code"] else None,
        requester_id=row["requester_id"],
        sla_status=sla_status,
        pending_user_reason=(
            PendingUserReason(row["pending_user_reason"]) if row["pending_user_reason"] else None
        ),
        has_active_vendor_request=active_vendor_org_id is not None,
    )
    return LockedTicket(row=dict(row), state=state, active_vendor_org_id=active_vendor_org_id)


def evaluate_or_raise(state: TicketState, request: ActionRequest) -> TransitionResult:
    """Call ``state_machine.evaluate`` and turn a denial straight into the
    ``ApplicationError`` the router should let propagate (via
    ``error_mapping``), so every action service can write
    ``result = evaluate_or_raise(...)`` instead of repeating the
    if-not-allowed-raise boilerplate ten times.
    """
    result = evaluate(state, request)
    if not result.allowed:
        raise error_for_denial(result.denial_code, result.denial_message)
    return result
