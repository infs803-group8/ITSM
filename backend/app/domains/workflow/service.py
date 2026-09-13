"""Write-path workflow action services (C025 onward).

Each class here is one workflow action's business logic: lock the ticket
(``action_engine.lock_ticket_state``), evaluate it against the state
machine (``action_engine.evaluate_or_raise``), apply the resulting write,
and record exactly one audit event. Never commits -- the router commits.
"""

from dataclasses import dataclass
from datetime import datetime

from app.common.request_context import RequestContext
from app.core.clock import utc_now
from app.core.enums import EventScope, EventType, UserRole
from app.domains.audit.service import AuditService
from app.domains.workflow.action_engine import evaluate_or_raise, lock_ticket_state
from app.domains.workflow.repository import WorkflowRepository
from app.domains.workflow.state_machine import ActionRequest, TicketStatus, WorkflowAction


@dataclass(frozen=True)
class WorkflowActionOutcome:
    status: TicketStatus
    event_id: int


class StartTicketService:
    """API-22 Start (C025): ASSIGNED or assignee-holding REOPENED ->
    IN_PROGRESS, current assignee only, no request body.
    """

    def __init__(self, database) -> None:
        self.database = database
        self.repository = WorkflowRepository(database)
        self.audit = AuditService(database)

    def start(
        self, *, ticket_id: int, actor: RequestContext, now: datetime | None = None
    ) -> WorkflowActionOutcome:
        now = now or utc_now()
        locked = lock_ticket_state(self.repository, ticket_id=ticket_id, now=now)
        request = ActionRequest(
            action=WorkflowAction.START,
            actor_role=UserRole(actor.role),
            actor_id=actor.user_id,
        )
        result = evaluate_or_raise(locked.state, request)

        # C025.03: only status_code changes -- sla_cycle_no/started_at/
        # deadline are left exactly as they are; Start is never a timer
        # reset point (result.cycle_effect is already "KEEP" for this
        # action, so there is nothing else this method needs to write).
        self.repository.apply_status_change(
            ticket_id=ticket_id, status_code=result.target_status.value
        )

        event_id = self.audit.append_event(
            ticket_id=ticket_id,
            event_type=EventType.HANDLING_STARTED,
            scope=EventScope.USER_VISIBLE,
            actor_id=actor.user_id,
        )
        return WorkflowActionOutcome(status=result.target_status, event_id=event_id)
