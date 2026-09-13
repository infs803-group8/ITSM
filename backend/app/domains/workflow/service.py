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
from app.core.errors import ApplicationError
from app.domains.audit.service import AuditService
from app.domains.sla.service import SlaCycleService
from app.domains.workflow.action_engine import evaluate_or_raise, lock_ticket_state
from app.domains.workflow.comment_gateway import insert_workflow_comment
from app.domains.workflow.repository import WorkflowRepository
from app.domains.workflow.state_machine import ActionRequest, TicketStatus, WorkflowAction


@dataclass(frozen=True)
class WorkflowActionOutcome:
    status: TicketStatus
    event_id: int
    #: Only set for actions that also write a comment (Request User Info
    #: today; possibly more of C027-C034 later) -- None for every action
    #: that does not, e.g. Start.
    comment_id: int | None = None


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



class RequestUserInfoService:
    """API-23 Request User Info (C026): IN_PROGRESS -> PENDING_USER/
    INFORMATION_REQUIRED, current assignee only. Pauses the current
    Engineering SLA cycle and starts the independent 120h User Timer, and
    writes a USER_VISIBLE WORKFLOW comment through the
    ``comment_gateway`` stopgap (see that module's own docstring for why
    -- B's comments domain is still an empty scaffold) rather than the
    plain HTTP API-20 endpoint, per C026.02.
    """

    def __init__(self, database) -> None:
        self.database = database
        self.repository = WorkflowRepository(database)
        self.audit = AuditService(database)
        self.sla = SlaCycleService(database)

    def request_user_info(
        self,
        *,
        ticket_id: int,
        actor: RequestContext,
        message: str,
        now: datetime | None = None,
    ) -> WorkflowActionOutcome:
        now = now or utc_now()
        if not message.strip():
            # Pydantic's min_length=1 on the request schema does not TRIM,
            # but schema.sql's chk_comments_message checks
            # CHAR_LENGTH(TRIM(message)) -- reject a whitespace-only
            # message here rather than let the INSERT fail at the
            # database with an opaque IntegrityError.
            raise ApplicationError(
                "VALIDATION_ERROR", "message must not be blank.", 422
            )

        locked = lock_ticket_state(self.repository, ticket_id=ticket_id, now=now)
        request = ActionRequest(
            action=WorkflowAction.REQUEST_USER_INFO,
            actor_role=UserRole(actor.role),
            actor_id=actor.user_id,
        )
        result = evaluate_or_raise(locked.state, request)
        assert result.cycle_effect == "PAUSE"
        assert result.target_pending_user_reason is not None

        # C026.03: end the current Engineering SLA cycle as PAUSED (no new
        # cycle starts until Resume/Issue Persists, C027) and compute the
        # independent 120h User Timer deadline.
        self.sla.pause_current_cycle(
            ticket_id=ticket_id,
            cycle_no=locked.row["sla_cycle_no"],
            actor_id=actor.user_id,
        )
        deadline = self.sla.compute_user_response_deadline(now=now)

        # C026.04: no other column needs clearing -- see
        # WorkflowRepository.apply_pending_user_transition's own
        # docstring for why, including Q09's "preserve already-occurred
        # overdue history" decision.
        self.repository.apply_pending_user_transition(
            ticket_id=ticket_id,
            status_code=result.target_status.value,
            pending_user_reason=result.target_pending_user_reason,
            pending_user_deadline=deadline,
        )

        # C026.02/.05: write the USER_VISIBLE/WORKFLOW comment plus its own
        # COMMENT_ADDED event, then the action's own USER_INFO_REQUESTED
        # event -- schema.sql's chk_ticket_events_comment_type requires
        # comment_id to be set ONLY on a COMMENT_ADDED event, so the two
        # events cannot be merged into one row.
        comment_id = insert_workflow_comment(
            self.database,
            ticket_id=ticket_id,
            author_id=actor.user_id,
            message=message,
            workflow_action=WorkflowAction.REQUEST_USER_INFO.value,
        )
        self.audit.append_event(
            ticket_id=ticket_id,
            event_type=EventType.COMMENT_ADDED,
            scope=EventScope.USER_VISIBLE,
            actor_id=actor.user_id,
            comment_id=comment_id,
        )
        event_id = self.audit.append_event(
            ticket_id=ticket_id,
            event_type=EventType.USER_INFO_REQUESTED,
            scope=EventScope.USER_VISIBLE,
            actor_id=actor.user_id,
            metadata={"pending_user_deadline": deadline.isoformat()},
        )
        return WorkflowActionOutcome(
            status=result.target_status, event_id=event_id, comment_id=comment_id
        )
