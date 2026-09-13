"""Write-path workflow action services (C025 onward).

Each class here is one workflow action's business logic: lock the ticket
(``action_engine.lock_ticket_state``), evaluate it against the state
machine (``action_engine.evaluate_or_raise``), apply the resulting write,
and record exactly one audit event. Never commits -- the router commits.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.common.request_context import RequestContext
from app.core.clock import utc_now
from app.core.enums import EventScope, EventType, UserRole
from app.core.errors import ApplicationError
from app.domains.assignment.repository import AssignmentRepository
from app.domains.assignment.service import AssignmentService
from app.domains.audit.service import AuditService
from app.domains.sla.service import SlaCycleService
from app.domains.workflow.action_engine import evaluate_or_raise, lock_ticket_state
from app.domains.workflow.comment_gateway import insert_workflow_comment
from app.domains.workflow.deadline_service import DeadlineService, PendingUserSnapshot, ResolvedSnapshot
from app.domains.vendor_workflow.repository import VendorWorkflowRepository
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


class ResumeTicketService:
    """API-24 Resume / Issue Persists (C027): PENDING_USER (either
    reason) -> IN_PROGRESS, ticket requester only. Shares one endpoint
    and one state-machine action (``WorkflowAction.USER_RESUME``) for
    both baseline-§4.3 flows, since they have the identical effect.
    """

    def __init__(self, database) -> None:
        self.database = database
        self.repository = WorkflowRepository(database)
        self.audit = AuditService(database)
        self.sla = SlaCycleService(database)
        self.deadlines = DeadlineService(database)

    def resume(
        self,
        *,
        ticket_id: int,
        actor: RequestContext,
        message: str,
        now: datetime | None = None,
    ) -> WorkflowActionOutcome:
        now = now or utc_now()
        if not message.strip():
            raise ApplicationError("VALIDATION_ERROR", "message must not be blank.", 422)

        locked = lock_ticket_state(self.repository, ticket_id=ticket_id, now=now)

        # C027.02/.06: unified Deadline Enforcement runs first, before any
        # actor/state validation -- an already-expired 120h window commits
        # its own auto-resolve outcome and raises USER_RESPONSE_WINDOW_
        # EXPIRED regardless of who called this or which of the two
        # PENDING_USER reasons is active. Only meaningful when the ticket
        # is actually PENDING_USER; any other source status is left to
        # evaluate_or_raise below to reject as INVALID_STATUS_TRANSITION.
        if locked.state.status == TicketStatus.PENDING_USER:
            self.deadlines.enforce_pending_user_not_expired(
                PendingUserSnapshot.from_row(locked.row),
                now=now,
                resolved_window_hours=self.sla.repository.get_resolved_window_hours(),
            )

        request = ActionRequest(
            action=WorkflowAction.USER_RESUME,
            actor_role=UserRole(actor.role),
            actor_id=actor.user_id,
        )
        result = evaluate_or_raise(locked.state, request)
        assert result.cycle_effect == "NEW"

        # C027.03/.04: one shared transition for both Resume and Issue
        # Persists -- see WorkflowRepository.apply_resume's own docstring
        # for why clearing the resolution_* columns is safe/required for
        # both paths.
        self.repository.apply_resume(ticket_id=ticket_id)

        comment_id = insert_workflow_comment(
            self.database,
            ticket_id=ticket_id,
            author_id=actor.user_id,
            message=message,
            workflow_action=WorkflowAction.USER_RESUME.value,
        )
        self.audit.append_event(
            ticket_id=ticket_id,
            event_type=EventType.COMMENT_ADDED,
            scope=EventScope.USER_VISIBLE,
            actor_id=actor.user_id,
            comment_id=comment_id,
        )

        # C027.05: fresh 48h cycle, cycle_no = previous + 1 -- writes its
        # own SLA_CYCLE_STARTED event.
        config = self.sla.load_config()
        self.sla.start_new_cycle(
            ticket_id=ticket_id,
            previous_cycle_no=locked.row["sla_cycle_no"],
            actor_id=actor.user_id,
            now=now,
            config=config,
        )

        event_id = self.audit.append_event(
            ticket_id=ticket_id,
            event_type=EventType.USER_RESUMED,
            scope=EventScope.USER_VISIBLE,
            actor_id=actor.user_id,
        )
        return WorkflowActionOutcome(
            status=result.target_status, event_id=event_id, comment_id=comment_id
        )



class EscalateTicketService:
    """API-25 Tier 2 Escalation (C028): IN_PROGRESS -> ASSIGNED, current
    Tier 1 assignee only, target must be an active, available Tier 2
    engineer with the ticket's category skill. ``state_machine._eval_
    escalate``'s ``cycle_effect`` is "KEEP" for this action, so no SLA
    repository/service call is made here at all -- the current cycle,
    deadline and any already-recorded overdue fact are left completely
    untouched (C028.03's "保留原 Cycle/Deadline/逾期事实").

    Reuses ``AssignmentRepository.get_target_engineer``/``apply_
    assignment`` from C024 rather than duplicating them here -- both
    actions ultimately write the same two ``tickets`` columns
    (``status_code``, ``assignee_id``), and C owns both ``assignment/``
    and ``workflow/``.
    """

    def __init__(self, database) -> None:
        self.database = database
        self.repository = WorkflowRepository(database)
        self.assignment_repository = AssignmentRepository(database)
        self.audit = AuditService(database)

    def escalate(
        self,
        *,
        ticket_id: int,
        actor: RequestContext,
        tier2_assignee_id: int,
        reason: str | None,
        now: datetime | None = None,
    ) -> WorkflowActionOutcome:
        now = now or utc_now()
        locked = lock_ticket_state(self.repository, ticket_id=ticket_id, now=now)

        # C028.02: target must be Active, Available, Tier 2, and skilled
        # for this ticket's category. state_machine._eval_escalate only
        # checks the target's ROLE (it has no concept of availability),
        # so the Active/Available/skill parts of this check are this
        # service's own responsibility, same division of labour as
        # AssignTicketService's target-eligibility check (C024).
        target = self.assignment_repository.get_target_engineer(
            tier2_assignee_id, locked.row["category_code"]
        )
        target_role = UserRole(target["role_code"]) if target is not None else None
        target_eligible = (
            target is not None
            and target_role == UserRole.ENGINEER_TIER2
            and bool(target["is_active"])
            and bool(target["is_available"])
            and bool(target["has_skill"])
        )
        if not target_eligible:
            raise ApplicationError(
                "ASSIGNEE_NOT_ELIGIBLE",
                "The selected assignee does not exist, is not an active and "
                "available Tier 2 engineer, or lacks the required skill.",
                422,
            )

        request = ActionRequest(
            action=WorkflowAction.ESCALATE,
            actor_role=UserRole(actor.role),
            actor_id=actor.user_id,
            target_assignee_role=target_role,
        )
        result = evaluate_or_raise(locked.state, request)
        assert result.cycle_effect == "KEEP"

        self.assignment_repository.apply_assignment(
            ticket_id=ticket_id,
            status_code=result.target_status.value,
            assignee_id=tier2_assignee_id,
        )

        # C028.04 (Q04 decision): no invented ESCALATED EventType -- an
        # escalation IS a reassignment, so it reuses REASSIGNED exactly
        # like a Manager-driven API-21 reassignment does, with metadata
        # recording who it moved from/to, the reason (if given), and an
        # explicit "escalation": true flag so a reader of the timeline
        # can still tell the two apart without a separate type.
        metadata: dict[str, object] = {
            "from_assignee_id": locked.row["assignee_id"],
            "assignee_id": tier2_assignee_id,
            "escalation": True,
        }
        if reason:
            metadata["reason"] = reason
        event_id = self.audit.append_event(
            ticket_id=ticket_id,
            event_type=EventType.REASSIGNED,
            scope=EventScope.USER_VISIBLE,
            actor_id=actor.user_id,
            metadata=metadata,
        )
        return WorkflowActionOutcome(status=result.target_status, event_id=event_id)


@dataclass(frozen=True)
class SubmitResolutionOutcome:
    status: TicketStatus
    event_id: int
    vendor_cancelled_event_id: int | None = None


class SubmitResolutionService:
    """API-28 Submit Resolution (C031): IN_PROGRESS or PENDING_VENDOR ->
    PENDING_USER/RESOLUTION_CONFIRMATION, current assignee only (the
    PENDING_VENDOR branch additionally requires the current Tier 2
    assignee specifically -- state_machine._eval_submit_resolution's own
    role check). ``cycle_effect`` is "KEEP" in both branches -- resolving
    does not itself pause or restart the Engineering SLA cycle; that is
    Confirm Resolution's (C032) job.

    The PENDING_VENDOR branch's ``vendor_request_effect`` is
    "CANCEL_ACTIVE" -- the assignee is resolving without waiting on the
    vendor's answer, so the now-moot ACTIVE request is cancelled rather
    than left dangling (and cancelling it clears the generated
    ``active_ticket_guard`` column, exactly like C030's MARK_RESPONDED
    path does, so a later ticket can still get its own new ACTIVE
    request). That branch writes two audit events -- VENDOR_CANCELLED
    then RESOLUTION_SUBMITTED -- for the same reason C026/C027 write two
    events for a combined comment+outcome action:
    ``chk_ticket_events_vendor_scope`` requires ``vendor_org_id`` set
    exactly when ``scope = 'VENDOR_SCOPE'``, so the vendor-scoped
    cancellation notice and the user-visible resolution notice cannot be
    the same row.
    """

    def __init__(self, database) -> None:
        self.database = database
        self.repository = WorkflowRepository(database)
        self.vendor_repository = VendorWorkflowRepository(database)
        self.audit = AuditService(database)
        self.sla = SlaCycleService(database)

    def submit_resolution(
        self,
        *,
        ticket_id: int,
        actor: RequestContext,
        resolution_summary: str,
        now: datetime | None = None,
    ) -> SubmitResolutionOutcome:
        now = now or utc_now()
        locked = lock_ticket_state(self.repository, ticket_id=ticket_id, now=now)

        request = ActionRequest(
            action=WorkflowAction.SUBMIT_RESOLUTION,
            actor_role=UserRole(actor.role),
            actor_id=actor.user_id,
        )
        result = evaluate_or_raise(locked.state, request)
        assert result.cycle_effect == "KEEP"

        vendor_cancelled_event_id = None
        if result.vendor_request_effect == "CANCEL_ACTIVE":
            binding = self.vendor_repository.get_active_binding(ticket_id=ticket_id)
            # Cannot be None here: state_machine only reaches this branch
            # from PENDING_VENDOR, which -- per chk_tickets_assignee_by_
            # status and this ticket's own has_active_vendor_request --
            # always has exactly one ACTIVE request to cancel.
            assert binding is not None
            self.vendor_repository.cancel_active_request(
                vendor_request_id=binding.vendor_request_id,
                cancelled_at=now,
                cancelled_by_id=actor.user_id,
                cancellation_reason="Resolved without waiting on vendor response.",
            )
            vendor_cancelled_event_id = self.audit.append_event(
                ticket_id=ticket_id,
                event_type=EventType.VENDOR_CANCELLED,
                scope=EventScope.VENDOR_SCOPE,
                actor_id=actor.user_id,
                vendor_org_id=binding.vendor_org_id,
                vendor_request_id=binding.vendor_request_id,
            )

        # Bug caught before pushing: this must be the 120h User Timer
        # (get_user_response_hours), the same config value C026's Request
        # User Info uses for its own PENDING_USER deadline -- NOT
        # get_resolved_window_hours (168h/7-day), which is the RESOLVED
        # -> auto_close_at window C032's Confirm Resolution needs
        # instead. Caught by re-reading sla/repository.py's own
        # docstrings while starting C032, which name both methods'
        # intended callers explicitly.
        pending_user_deadline = now + timedelta(
            hours=self.sla.repository.get_user_response_hours()
        )
        self.repository.apply_submit_resolution(
            ticket_id=ticket_id,
            pending_user_deadline=pending_user_deadline,
            resolution_summary=resolution_summary,
        )

        event_id = self.audit.append_event(
            ticket_id=ticket_id,
            event_type=EventType.RESOLUTION_SUBMITTED,
            scope=EventScope.USER_VISIBLE,
            actor_id=actor.user_id,
        )
        return SubmitResolutionOutcome(
            status=result.target_status,
            event_id=event_id,
            vendor_cancelled_event_id=vendor_cancelled_event_id,
        )


@dataclass(frozen=True)
class ConfirmResolutionOutcome:
    status: TicketStatus
    event_id: int


class ConfirmResolutionService:
    """API-29 Confirm Resolution (C032): PENDING_USER/RESOLUTION_
    CONFIRMATION -> RESOLVED, ticket requester only, no request body.
    ``cycle_effect`` is "NONE" -- confirming touches no Engineering SLA
    cycle bookkeeping at all (per action_engine's own vocabulary, "NONE"
    is reserved for system-closure-shaped actions; this one just happens
    to be requester-driven rather than a background job).

    ``resolution_summary`` was already written at Submit Resolution
    (C031); this only sets ``resolution_type=USER_CONFIRMED``,
    ``resolved_at=now``, and the 7-day ``auto_close_at`` -- the value
    C036's SLA monitor job will later read to auto-close the ticket if
    the requester never explicitly closes it (C034).

    ``DeadlineService.enforce_pending_user_not_expired``'s own docstring
    names this action (alongside C027's Resume) as one of its two
    callers -- the 120h User Timer could already have expired by the
    time this request arrives, in which case the ticket auto-resolves
    as AUTO_CONFIRMATION_TIMEOUT instead and this call reports
    USER_RESPONSE_WINDOW_EXPIRED (409) rather than confirming a
    resolution outcome that database state no longer matches. Missed on
    first pass and caught while starting C033's Reopen, whose sibling
    guard (``enforce_resolved_not_auto_closed``) made it obvious this one
    had gone unused for its intended second caller.
    """

    def __init__(self, database) -> None:
        self.database = database
        self.repository = WorkflowRepository(database)
        self.audit = AuditService(database)
        self.sla = SlaCycleService(database)
        self.deadlines = DeadlineService(database)

    def confirm_resolution(
        self, *, ticket_id: int, actor: RequestContext, now: datetime | None = None
    ) -> ConfirmResolutionOutcome:
        now = now or utc_now()
        locked = lock_ticket_state(self.repository, ticket_id=ticket_id, now=now)
        if locked.state.status == TicketStatus.PENDING_USER:
            self.deadlines.enforce_pending_user_not_expired(
                PendingUserSnapshot.from_row(locked.row),
                now=now,
                resolved_window_hours=self.sla.repository.get_resolved_window_hours(),
            )

        request = ActionRequest(
            action=WorkflowAction.CONFIRM_RESOLUTION,
            actor_role=UserRole(actor.role),
            actor_id=actor.user_id,
        )
        result = evaluate_or_raise(locked.state, request)
        assert result.cycle_effect == "NONE"
        assert result.resolution_type is not None

        auto_close_at = self.sla.compute_auto_close_deadline(resolved_at=now)
        self.repository.apply_confirm_resolution(
            ticket_id=ticket_id,
            resolution_type=result.resolution_type.value,
            resolved_at=now,
            auto_close_at=auto_close_at,
            last_resolved_assignee_id=locked.row["assignee_id"],
        )

        event_id = self.audit.append_event(
            ticket_id=ticket_id,
            event_type=EventType.RESOLUTION_CONFIRMED,
            scope=EventScope.USER_VISIBLE,
            actor_id=actor.user_id,
        )
        return ConfirmResolutionOutcome(status=result.target_status, event_id=event_id)


@dataclass(frozen=True)
class ReopenOutcome:
    status: TicketStatus
    event_id: int
    comment_id: int
    assignee_id: int | None


class ReopenTicketService:
    """API-30 Reopen (C033): RESOLVED -> REOPENED, ticket requester only,
    before ``auto_close_at`` (``DeadlineService.enforce_resolved_not_auto_
    closed``'s own docstring names this action, alongside Manual Close,
    as its two callers). ``cycle_effect`` is "NEW" -- reopening starts a
    fresh Engineering SLA cycle, same shape as C027's Resume.

    ``last_resolved_assignee_id`` (set by C032's Confirm Resolution, and
    by C018's auto-resolve paths) is this service's own preference, not
    a state_machine concept: if that engineer is still active/available/
    skilled for the ticket's category, they keep the ticket; otherwise
    this falls back to the same ``AssignmentService.assign_new_ticket``
    selection C022/C023 use for a brand-new ticket, which itself may
    still return ``None`` (no eligible engineer at all) -- Reopen still
    succeeds in that case, just with no assignee set yet.
    """

    def __init__(self, database) -> None:
        self.database = database
        self.repository = WorkflowRepository(database)
        self.assignment_repository = AssignmentRepository(database)
        self.assignment_service = AssignmentService(database)
        self.audit = AuditService(database)
        self.sla = SlaCycleService(database)
        self.deadlines = DeadlineService(database)

    def reopen(
        self,
        *,
        ticket_id: int,
        actor: RequestContext,
        reason: str,
        now: datetime | None = None,
    ) -> ReopenOutcome:
        now = now or utc_now()
        locked = lock_ticket_state(self.repository, ticket_id=ticket_id, now=now)
        if locked.state.status == TicketStatus.RESOLVED:
            self.deadlines.enforce_resolved_not_auto_closed(
                ResolvedSnapshot.from_row(locked.row), now=now
            )

        request = ActionRequest(
            action=WorkflowAction.REOPEN,
            actor_role=UserRole(actor.role),
            actor_id=actor.user_id,
        )
        result = evaluate_or_raise(locked.state, request)
        assert result.cycle_effect == "NEW"

        previous_assignee_id = locked.row["last_resolved_assignee_id"]
        assignee_id = self._pick_assignee(
            ticket_id=ticket_id,
            previous_assignee_id=previous_assignee_id,
            category_code=locked.row["category_code"],
        )

        self.repository.apply_reopen(ticket_id=ticket_id, assignee_id=assignee_id)

        comment_id = insert_workflow_comment(
            self.database,
            ticket_id=ticket_id,
            author_id=actor.user_id,
            message=reason,
            workflow_action=WorkflowAction.REOPEN.value,
        )
        self.audit.append_event(
            ticket_id=ticket_id,
            event_type=EventType.COMMENT_ADDED,
            scope=EventScope.USER_VISIBLE,
            actor_id=actor.user_id,
            comment_id=comment_id,
        )

        config = self.sla.load_config()
        self.sla.start_new_cycle(
            ticket_id=ticket_id,
            previous_cycle_no=locked.row["sla_cycle_no"],
            actor_id=actor.user_id,
            now=now,
            config=config,
        )

        event_id = self.audit.append_event(
            ticket_id=ticket_id,
            event_type=EventType.TICKET_REOPENED,
            scope=EventScope.USER_VISIBLE,
            actor_id=actor.user_id,
        )
        return ReopenOutcome(
            status=result.target_status,
            event_id=event_id,
            comment_id=comment_id,
            assignee_id=assignee_id,
        )

    def _pick_assignee(
        self, *, ticket_id: int, previous_assignee_id: int | None, category_code: str
    ) -> int | None:
        if previous_assignee_id is not None:
            target = self.assignment_repository.get_target_engineer(
                previous_assignee_id, category_code
            )
            previous_still_eligible = (
                target is not None
                and bool(target["is_active"])
                and bool(target["is_available"])
                and bool(target["has_skill"])
            )
            if previous_still_eligible:
                return previous_assignee_id
        # AssignmentService.assign_new_ticket accepts ticket_id purely to
        # match the frozen InitialAssignmentService Protocol signature --
        # its own selection algorithm only needs category_code -- but
        # passing the real id (rather than a placeholder) costs nothing
        # and keeps this call unremarkable if that ever changes.
        return self.assignment_service.assign_new_ticket(
            ticket_id=ticket_id, category_code=category_code
        )
