"""Initial ticket-creation orchestration (C023).

C023 splits ownership deliberately (per the task doc: "B owns API-15; C
provides the internal Service and tests"): Member B owns API-15 and
``app.domains.tickets.*`` and is responsible for inserting the bare
ticket row (title, description, category, priority, requester_id) inside
their own transaction; this module is C's contribution -- the function
B's handler calls immediately after that insert, inside the SAME
transaction and before committing, to run the rest of the creation
sequence (C023.01):

    1. lock ``assignment_control`` (``AssignmentService.assign_new_ticket``
       does this internally, C022.04)
    2. pick a Tier 1 candidate, or find none
    3. start the first SLA cycle (cycle_no = 1)
    4. resolve the ticket's final status: ``ASSIGNED`` + assignee, or
       ``UNASSIGNED`` + null -- ``NEW`` must never survive past this call
       (C023.02; it is a transient, creation-only value per baseline §4.1
       and ``state_machine``'s own module docstring)
    5. write ``SLA_CYCLE_STARTED`` and, only when a candidate was found,
       ``AUTO_ASSIGNED``

C023.03 (write-once responsibility, so B and C never duplicate an event):
``TICKET_CREATED`` is B's, written at the point of insert, before this
module is ever called. ``SLA_CYCLE_STARTED`` and ``AUTO_ASSIGNED`` are
written here and nowhere else.

C023.04: this module takes ``requester_id``/``assignee_id`` in exactly the
shape the ``tickets`` table already uses (``BIGINT UNSIGNED`` user ids) --
it does not introduce a second name for the same concept.

C023.05: nothing in this module commits. If any step here raises, the
caller's transaction (B's, wrapping the ticket insert together with this
call) rolls back everything together -- the ticket row, ``last_assigned_at``,
the SLA cycle columns and every ``TicketEvent`` written in this call stay
all-or-nothing as one unit; there is deliberately no local try/except here
that would let a partial result slip through.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.enums import EventScope, EventType
from app.domains.assignment.service import AssignmentService
from app.domains.audit.service import AuditService
from app.domains.sla.service import SlaCycleService
from app.domains.workflow.repository import WorkflowRepository
from app.domains.workflow.state_machine import TicketStatus


@dataclass(frozen=True)
class TicketInitializationOutcome:
    """What B's API-15 handler needs back to shape its HTTP response."""

    status: TicketStatus
    assignee_id: int | None
    sla_cycle_no: int
    sla_deadline: datetime


def initialize_ticket_workflow(
    database: Session,
    *,
    ticket_id: int,
    category_code: str,
    now: datetime,
) -> TicketInitializationOutcome:
    """Run every C023.01 step after B has inserted the bare ticket row.

    This function does not lock or re-read the ``tickets`` row itself --
    only ``AssignmentService`` takes a lock here (``assignment_control``,
    per C022.04). B's insert (and whatever row lock it implies) is
    expected to already be part of the same open transaction.
    """
    assignment_service = AssignmentService(database)
    assignee_id = assignment_service.assign_new_ticket(
        ticket_id=ticket_id, category_code=category_code
    )

    sla_service = SlaCycleService(database)
    config = sla_service.load_config()
    window = sla_service.start_first_cycle(
        ticket_id=ticket_id, actor_id=None, now=now, config=config
    )

    status = TicketStatus.ASSIGNED if assignee_id is not None else TicketStatus.UNASSIGNED
    WorkflowRepository(database).apply_initial_assignment(
        ticket_id=ticket_id, status=status.value, assignee_id=assignee_id
    )

    if assignee_id is not None:
        AuditService(database).append_event(
            ticket_id=ticket_id,
            event_type=EventType.AUTO_ASSIGNED,
            scope=EventScope.USER_VISIBLE,
            actor_id=None,
            metadata={"assignee_id": assignee_id},
        )

    return TicketInitializationOutcome(
        status=status,
        assignee_id=assignee_id,
        sla_cycle_no=window.cycle_no,
        sla_deadline=window.deadline,
    )
