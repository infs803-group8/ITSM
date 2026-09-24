"""Initial auto-assignment service (C022).

Implements ``app.contracts.initial_assignment.InitialAssignmentService``.
Only chooses an assignee; it never writes the ticket row itself (status,
``assignee_id``, the first SLA cycle, or the ``TICKET_CREATED``/
``AUTO_ASSIGNED`` audit events all stay the create-ticket transaction's
job -- that wiring is C023, into Member B's API-15 handler). Keeping this
service scoped to selection alone lets C023 call it from inside whatever
shape B's create-ticket transaction ends up taking, without this service
assuming it.
"""

from app.core.clock import as_utc, utc_now
from app.domains.assignment.ranking import Candidate, pick_winner
from app.domains.assignment.repository import AssignmentRepository


class AssignmentService:
    def __init__(self, database) -> None:
        self.database = database
        self.repository = AssignmentRepository(database)

    def assign_new_ticket(self, *, ticket_id: int, category_code: str) -> int | None:
        """C022.04: lock the ``assignment_control`` singleton first, then
        read candidates and update the winner's ``last_assigned_at``
        inside that same locked transaction -- the caller commits.

        ``ticket_id`` is accepted (and not otherwise used) purely to match
        the frozen ``InitialAssignmentService`` Protocol signature; the
        selection algorithm itself only needs the category.

        Returns ``None`` only for a genuine "no eligible engineer" outcome
        (C022.05) -- a database error propagates as an exception rather
        than being disguised as a normal ``None``/UNASSIGNED result.
        """
        self.repository.lock_assignment_control()
        rows = self.repository.list_candidate_engineers(category_code)
        candidates = [
            Candidate(
                user_id=row["user_id"],
                active_load=row["active_load"],
                last_assigned_at=row["last_assigned_at"],
            )
            for row in rows
        ]
        winner = pick_winner(candidates)
        if winner is None:
            return None
        self.repository.mark_last_assigned(user_id=winner.user_id, when=utc_now())
        return winner.user_id


from dataclasses import dataclass  # noqa: E402
from datetime import datetime  # noqa: E402

from app.common.request_context import RequestContext  # noqa: E402
from app.core.enums import EventScope, EventType, UserRole  # noqa: E402
from app.core.errors import ApplicationError  # noqa: E402
from app.domains.audit.service import AuditService  # noqa: E402
from app.domains.workflow.error_mapping import error_for_denial  # noqa: E402
from app.domains.workflow.state_machine import (  # noqa: E402
    ActionRequest,
    PendingUserReason,
    SlaStatus,
    TicketState,
    TicketStatus,
    WorkflowAction,
    evaluate,
)


@dataclass(frozen=True)
class AssignOutcome:
    status: TicketStatus
    event_id: int


class AssignTicketService:
    """API-21 Assign/Reassign (C024). A distinct service from
    ``AssignmentService`` (C022's *initial*, system-driven auto-assignment):
    this one is the Manager-driven, HTTP-facing action, with its own
    eligibility checks and event types (``ASSIGNED``/``REASSIGNED`` rather
    than ``AUTO_ASSIGNED``), even though both ultimately call the same
    ``AssignmentRepository`` for the target engineer's row.
    """

    def __init__(self, database) -> None:
        self.database = database
        self.repository = AssignmentRepository(database)
        self.audit = AuditService(database)

    def assign_ticket(
        self,
        *,
        ticket_id: int,
        actor: RequestContext,
        assignee_id: int,
        reason: str | None,
        now: datetime,
    ) -> AssignOutcome:
        """Returns the ticket's new status and the written event's id.
        Raises ``ApplicationError`` for
        every denied/invalid case (404 not found, 422 same-assignee or
        ineligible target, or whatever ``error_mapping`` resolves the
        state machine's denial to). Never commits -- the router commits.
        """
        row = self.repository.get_ticket_snapshot_for_assign(ticket_id)
        if row is None:
            raise ApplicationError(
                "RESOURCE_NOT_FOUND", "The requested resource was not found.", 404
            )

        if assignee_id == row["assignee_id"]:
            raise ApplicationError(
                "ASSIGNEE_NOT_ELIGIBLE",
                "The selected assignee is already assigned to this ticket.",
                422,
            )

        target = self.repository.get_target_engineer(assignee_id, row["category_code"])
        target_role = UserRole(target["role_code"]) if target is not None else None
        target_eligible_shape = (
            target is not None and bool(target["is_active"]) and bool(target["has_skill"])
        )
        if not target_eligible_shape:
            raise ApplicationError(
                "ASSIGNEE_NOT_ELIGIBLE",
                "The selected assignee does not exist, is inactive, or lacks the required skill.",
                422,
            )
        target_available = bool(target["is_available"])

        active_vendor_org_id = self.repository.get_active_vendor_request_org(ticket_id)

        # C024.02: judge overdue-ness from the real deadline, not only the
        # (possibly lagging, job-maintained) stored sla_status_code.
        is_overdue_now = row["sla_status_code"] == "OVERDUE" or (
            row["sla_deadline"] is not None and now >= as_utc(row["sla_deadline"])
        )
        sla_status = SlaStatus.OVERDUE if is_overdue_now else SlaStatus(row["sla_status_code"])

        state = TicketState(
            status=TicketStatus(row["status_code"]),
            assignee_id=row["assignee_id"],
            assignee_role=(
                UserRole(row["assignee_role_code"]) if row["assignee_role_code"] else None
            ),
            requester_id=row["requester_id"],
            sla_status=sla_status,
            pending_user_reason=(
                PendingUserReason(row["pending_user_reason"])
                if row["pending_user_reason"]
                else None
            ),
            has_active_vendor_request=active_vendor_org_id is not None,
        )
        request = ActionRequest(
            action=WorkflowAction.ASSIGN,
            actor_role=UserRole(actor.role),
            actor_id=actor.user_id,
            target_assignee_role=target_role,
            target_assignee_available=target_available,
        )
        result = evaluate(state, request)
        if not result.allowed:
            raise error_for_denial(result.denial_code, result.denial_message)

        self.repository.apply_assignment(
            ticket_id=ticket_id,
            status_code=result.target_status.value,
            assignee_id=assignee_id,
        )

        event_type = EventType.ASSIGNED if row["assignee_id"] is None else EventType.REASSIGNED
        metadata: dict[str, object] = {"assignee_id": assignee_id}
        if reason:
            metadata["reason"] = reason
        event_id = self.audit.append_event(
            ticket_id=ticket_id,
            event_type=event_type,
            scope=EventScope.USER_VISIBLE,
            actor_id=actor.user_id,
            metadata=metadata,
        )

        return AssignOutcome(status=result.target_status, event_id=event_id)
