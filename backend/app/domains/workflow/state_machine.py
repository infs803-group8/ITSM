"""Pure ticket workflow state machine (baseline v6.0 §4).

This module answers exactly one question: *from this ticket snapshot, is
this actor allowed to perform this action, and what would the resulting
status/fields be?* It never touches the database, S3, or HTTP, and it
never reads the clock -- deadline enforcement (now vs. a deadline) is a
separate concern owned by ``workflow/deadline_service.py`` (task C018/
C019/C020). Both the write-path services and ``WorkflowReadModel``
(task C021, "available actions") call the same ``evaluate`` function so
they can never silently disagree; per C016.05, listing an action as
available at read time does NOT exempt the write path from calling
``evaluate`` again with the concrete target before committing anything.

``NEW`` from baseline §4.1 is intentionally not a member of
``TicketStatus`` transitions handled here: it only exists inside the
API-15 creation transaction and must resolve to ``ASSIGNED`` or
``UNASSIGNED`` before that transaction commits, so it is never a
starting state an actor can act on afterwards.

SLA status (``SlaStatus``: ON_TRACK/AT_RISK/OVERDUE/PAUSED/MET) is
tracked on the ticket alongside, but deliberately kept out of
``TicketStatus`` (core.enums) -- see baseline §4.2 ("AT_RISK/OVERDUE
是 SLA 状态，不是生命周期状态") and C016.03.
"""

from dataclasses import dataclass
from enum import StrEnum

from app.core.enums import TicketStatus, UserRole

# ---------------------------------------------------------------------------
# Domain enums that are not part of the public OpenAPI contract in
# app.core.enums, but are fixed by CHECK constraints in schema.sql. Keep
# these two files in sync.
# ---------------------------------------------------------------------------


class PendingUserReason(StrEnum):
    """schema.sql: chk_tickets_pending_user."""

    INFORMATION_REQUIRED = "INFORMATION_REQUIRED"
    RESOLUTION_CONFIRMATION = "RESOLUTION_CONFIRMATION"


class SlaStatus(StrEnum):
    """schema.sql: sla_statuses seed rows. Not a lifecycle status."""

    ON_TRACK = "ON_TRACK"
    AT_RISK = "AT_RISK"
    OVERDUE = "OVERDUE"
    PAUSED = "PAUSED"
    MET = "MET"


class ResolutionType(StrEnum):
    """schema.sql: chk_tickets_resolution."""

    USER_CONFIRMED = "USER_CONFIRMED"
    AUTO_NO_USER_RESPONSE = "AUTO_NO_USER_RESPONSE"
    AUTO_CONFIRMATION_TIMEOUT = "AUTO_CONFIRMATION_TIMEOUT"


class ClosureType(StrEnum):
    """schema.sql: chk_tickets_closure."""

    MANUAL_USER = "MANUAL_USER"
    AUTO_AFTER_7_DAYS = "AUTO_AFTER_7_DAYS"


class WorkflowAction(StrEnum):
    """One entry per row of baseline §4.3 plus the §4.5 assign matrix.

    ``USER_RESUME`` covers both "Resume" (from INFORMATION_REQUIRED) and
    "Issue Persists" (from RESOLUTION_CONFIRMATION) -- baseline §4.2/4.3
    give both the identical effect (IN_PROGRESS + new cycle) and both are
    the same API-24 call, which is also why core.enums.EventType has a
    single USER_RESUMED event for it.
    """

    ASSIGN = "ASSIGN"
    ESCALATE = "ESCALATE"
    START = "START"
    REQUEST_USER_INFO = "REQUEST_USER_INFO"
    USER_RESUME = "USER_RESUME"
    REQUEST_VENDOR = "REQUEST_VENDOR"
    VENDOR_RESPONSE = "VENDOR_RESPONSE"
    SUBMIT_RESOLUTION = "SUBMIT_RESOLUTION"
    CONFIRM_RESOLUTION = "CONFIRM_RESOLUTION"
    REOPEN = "REOPEN"
    MANUAL_CLOSE = "MANUAL_CLOSE"
    AUTO_RESOLVE_NO_RESPONSE = "AUTO_RESOLVE_NO_RESPONSE"
    AUTO_RESOLVE_CONFIRMATION_TIMEOUT = "AUTO_RESOLVE_CONFIRMATION_TIMEOUT"
    AUTO_CLOSE = "AUTO_CLOSE"


#: Actions the deadline service (never a human) performs. These skip the
#: normal actor/ownership checks -- there is no HTTP endpoint for them.
SYSTEM_ONLY_ACTIONS = frozenset(
    {
        WorkflowAction.AUTO_RESOLVE_NO_RESPONSE,
        WorkflowAction.AUTO_RESOLVE_CONFIRMATION_TIMEOUT,
        WorkflowAction.AUTO_CLOSE,
    }
)

#: Actions a human actor can be shown/attempt. Used by WorkflowReadModel
#: to build ``available_actions`` -- never includes the system-only set.
USER_FACING_ACTIONS = frozenset(WorkflowAction) - SYSTEM_ONLY_ACTIONS


# ---------------------------------------------------------------------------
# Inputs / outputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TicketState:
    """The minimal ticket snapshot the state machine needs to decide.

    Deliberately NOT the Ticket ORM row -- callers build this from
    whatever repository read they already did, so this module has zero
    dependency on Member B's Ticket model.
    """

    status: TicketStatus
    assignee_id: int | None
    assignee_role: UserRole | None
    requester_id: int
    sla_status: SlaStatus
    pending_user_reason: PendingUserReason | None = None
    has_active_vendor_request: bool = False


@dataclass(frozen=True)
class ActionRequest:
    action: WorkflowAction
    actor_role: UserRole | None
    actor_id: int | None
    actor_vendor_org_id: int | None = None
    #: Only meaningful for ASSIGN. Omit to ask "could SOME target make
    #: this action legal from this state" (what WorkflowReadModel wants);
    #: provide it to fully validate one concrete target (what the write
    #: path must do before committing).
    target_assignee_role: UserRole | None = None
    target_assignee_available: bool | None = None
    #: Only meaningful for VENDOR_RESPONSE: the ticket's current active
    #: VendorRequest's organisation, so a vendor actor from a *different*
    #: organisation is rejected even though the ticket has an active
    #: request.
    active_vendor_request_org_id: int | None = None


@dataclass(frozen=True)
class TransitionResult:
    allowed: bool
    target_status: TicketStatus | None = None
    target_pending_user_reason: PendingUserReason | None = None
    #: "NEW" starts a fresh 48h cycle, "PAUSE" ends the current cycle
    #: without starting a new one, "KEEP" leaves the current cycle alone,
    #: "NONE" means no cycle bookkeeping change (system closure actions).
    cycle_effect: str = "NONE"
    vendor_request_effect: str | None = (
        None  # None | "CREATE_ACTIVE" | "MARK_RESPONDED" | "CANCEL_ACTIVE"
    )
    resolution_type: ResolutionType | None = None
    closure_type: ClosureType | None = None
    denial_code: str | None = None
    denial_message: str | None = None

    @staticmethod
    def deny(code: str, message: str) -> "TransitionResult":
        return TransitionResult(allowed=False, denial_code=code, denial_message=message)


_INVALID_TRANSITION = "INVALID_STATUS_TRANSITION"
_TICKET_CLOSED = "TICKET_CLOSED"
_NOT_ASSIGNEE = "NOT_TICKET_ASSIGNEE"
_NOT_REQUESTER = "NOT_TICKET_REQUESTER"
_VENDOR_ORG_MISMATCH = "VENDOR_ORG_MISMATCH"
_TARGET_NOT_ELIGIBLE = "TARGET_ASSIGNEE_NOT_ELIGIBLE"


def _is_current_assignee(state: TicketState, request: ActionRequest) -> bool:
    return state.assignee_id is not None and state.assignee_id == request.actor_id


def _is_requester(state: TicketState, request: ActionRequest) -> bool:
    return state.requester_id == request.actor_id


def _eval_assign(state: TicketState, request: ActionRequest) -> TransitionResult:
    """API-21 Assign/Reassign matrix (baseline §4.5)."""
    if request.actor_role != UserRole.SERVICE_DESK_MANAGER:
        return TransitionResult.deny(
            "ROLE_NOT_PERMITTED", "Only a Service Desk Manager may assign or reassign a ticket."
        )

    def eligible(required_tiers: set[UserRole]) -> TransitionResult:
        if request.target_assignee_role is None:
            # No concrete target given: report the class of action as
            # available without claiming any specific target is valid.
            return TransitionResult(
                allowed=True, target_status=TicketStatus.ASSIGNED, cycle_effect="KEEP"
            )
        if request.target_assignee_role not in required_tiers:
            return TransitionResult.deny(
                _TARGET_NOT_ELIGIBLE, "The selected assignee's tier is not eligible."
            )
        if request.target_assignee_available is False:
            return TransitionResult.deny(
                _TARGET_NOT_ELIGIBLE, "The selected assignee is not available."
            )
        return TransitionResult(
            allowed=True, target_status=TicketStatus.ASSIGNED, cycle_effect="KEEP"
        )

    both_tiers = {UserRole.ENGINEER_TIER1, UserRole.ENGINEER_TIER2}
    tier2_only = {UserRole.ENGINEER_TIER2}

    if state.status == TicketStatus.UNASSIGNED and state.assignee_id is None:
        if state.sla_status == SlaStatus.OVERDUE:
            return eligible(tier2_only)
        return eligible(both_tiers)

    if (
        state.status in {TicketStatus.ASSIGNED, TicketStatus.IN_PROGRESS}
        and state.sla_status == SlaStatus.OVERDUE
    ):
        return eligible(tier2_only)

    if state.status == TicketStatus.PENDING_USER:
        if state.assignee_role == UserRole.ENGINEER_TIER1:
            result = eligible(both_tiers)
        else:
            result = eligible(tier2_only)
        if result.allowed:
            result = TransitionResult(
                allowed=True,
                target_status=TicketStatus.PENDING_USER,
                target_pending_user_reason=state.pending_user_reason,
                cycle_effect="KEEP",
            )
        return result

    if state.status == TicketStatus.PENDING_VENDOR and state.sla_status == SlaStatus.OVERDUE:
        if not state.has_active_vendor_request:
            return TransitionResult.deny(
                _INVALID_TRANSITION,
                "PENDING_VENDOR reassignment requires an active vendor request.",
            )
        result = eligible(tier2_only)
        if result.allowed:
            result = TransitionResult(
                allowed=True,
                target_status=TicketStatus.PENDING_VENDOR,
                vendor_request_effect=None,
                cycle_effect="KEEP",
            )
        return result

    if state.status == TicketStatus.REOPENED and state.assignee_id is None:
        return eligible(both_tiers)

    return TransitionResult.deny(
        _INVALID_TRANSITION, "This ticket is not in a state that allows assign/reassign."
    )


def _eval_escalate(state: TicketState, request: ActionRequest) -> TransitionResult:
    if state.status != TicketStatus.IN_PROGRESS:
        return TransitionResult.deny(
            _INVALID_TRANSITION, "Escalation requires an in-progress ticket."
        )
    if request.actor_role != UserRole.ENGINEER_TIER1 or not _is_current_assignee(state, request):
        return TransitionResult.deny(
            _NOT_ASSIGNEE, "Only the ticket's current Tier 1 assignee may escalate it."
        )
    if (
        request.target_assignee_role is not None
        and request.target_assignee_role != UserRole.ENGINEER_TIER2
    ):
        return TransitionResult.deny(
            _TARGET_NOT_ELIGIBLE, "Escalation must target a Tier 2 engineer."
        )
    return TransitionResult(allowed=True, target_status=TicketStatus.ASSIGNED, cycle_effect="KEEP")


def _eval_start(state: TicketState, request: ActionRequest) -> TransitionResult:
    if state.status not in {TicketStatus.ASSIGNED, TicketStatus.REOPENED}:
        return TransitionResult.deny(
            _INVALID_TRANSITION, "Only an assigned or reopened ticket can be started."
        )
    if not _is_current_assignee(state, request):
        return TransitionResult.deny(
            _NOT_ASSIGNEE, "Only the ticket's current assignee may start it."
        )
    return TransitionResult(
        allowed=True, target_status=TicketStatus.IN_PROGRESS, cycle_effect="KEEP"
    )


def _eval_request_user_info(state: TicketState, request: ActionRequest) -> TransitionResult:
    if state.status != TicketStatus.IN_PROGRESS:
        return TransitionResult.deny(
            _INVALID_TRANSITION, "Requesting user info requires an in-progress ticket."
        )
    if not _is_current_assignee(state, request):
        return TransitionResult.deny(
            _NOT_ASSIGNEE, "Only the ticket's current assignee may request user info."
        )
    return TransitionResult(
        allowed=True,
        target_status=TicketStatus.PENDING_USER,
        target_pending_user_reason=PendingUserReason.INFORMATION_REQUIRED,
        cycle_effect="PAUSE",
    )


def _eval_user_resume(state: TicketState, request: ActionRequest) -> TransitionResult:
    if state.status != TicketStatus.PENDING_USER:
        return TransitionResult.deny(
            _INVALID_TRANSITION, "Resuming requires a pending-user ticket."
        )
    if not _is_requester(state, request):
        return TransitionResult.deny(_NOT_REQUESTER, "Only the ticket's requester may resume it.")
    return TransitionResult(
        allowed=True, target_status=TicketStatus.IN_PROGRESS, cycle_effect="NEW"
    )


def _eval_request_vendor(state: TicketState, request: ActionRequest) -> TransitionResult:
    if state.status != TicketStatus.IN_PROGRESS:
        return TransitionResult.deny(
            _INVALID_TRANSITION, "Requesting vendor help requires an in-progress ticket."
        )
    if request.actor_role != UserRole.ENGINEER_TIER2 or not _is_current_assignee(state, request):
        return TransitionResult.deny(
            _NOT_ASSIGNEE, "Only the ticket's current Tier 2 assignee may request vendor help."
        )
    if state.has_active_vendor_request:
        return TransitionResult.deny(
            "VENDOR_REQUEST_ALREADY_ACTIVE", "This ticket already has an active vendor request."
        )
    return TransitionResult(
        allowed=True,
        target_status=TicketStatus.PENDING_VENDOR,
        vendor_request_effect="CREATE_ACTIVE",
        cycle_effect="KEEP",
    )


def _eval_vendor_response(state: TicketState, request: ActionRequest) -> TransitionResult:
    if state.status != TicketStatus.PENDING_VENDOR:
        return TransitionResult.deny(
            _INVALID_TRANSITION, "Vendor response requires a pending-vendor ticket."
        )
    if request.actor_role != UserRole.EXTERNAL_VENDOR:
        return TransitionResult.deny(
            _NOT_ASSIGNEE, "Only a vendor actor may submit a vendor response."
        )
    if not state.has_active_vendor_request:
        return TransitionResult.deny(
            "NO_ACTIVE_VENDOR_REQUEST", "There is no active vendor request on this ticket."
        )
    if (
        request.active_vendor_request_org_id is not None
        and request.actor_vendor_org_id != request.active_vendor_request_org_id
    ):
        return TransitionResult.deny(
            _VENDOR_ORG_MISMATCH, "This vendor organisation does not own the active request."
        )
    return TransitionResult(
        allowed=True,
        target_status=TicketStatus.IN_PROGRESS,
        vendor_request_effect="MARK_RESPONDED",
        cycle_effect="KEEP",
    )


def _eval_submit_resolution(state: TicketState, request: ActionRequest) -> TransitionResult:
    if state.status == TicketStatus.IN_PROGRESS:
        if not _is_current_assignee(state, request):
            return TransitionResult.deny(
                _NOT_ASSIGNEE, "Only the ticket's current assignee may submit a resolution."
            )
        return TransitionResult(
            allowed=True,
            target_status=TicketStatus.PENDING_USER,
            target_pending_user_reason=PendingUserReason.RESOLUTION_CONFIRMATION,
            cycle_effect="KEEP",
        )
    if state.status == TicketStatus.PENDING_VENDOR:
        if request.actor_role != UserRole.ENGINEER_TIER2 or not _is_current_assignee(
            state, request
        ):
            return TransitionResult.deny(
                _NOT_ASSIGNEE,
                "Only the ticket's current Tier 2 assignee may resolve without waiting on vendor.",
            )
        return TransitionResult(
            allowed=True,
            target_status=TicketStatus.PENDING_USER,
            target_pending_user_reason=PendingUserReason.RESOLUTION_CONFIRMATION,
            vendor_request_effect="CANCEL_ACTIVE",
            cycle_effect="KEEP",
        )
    return TransitionResult.deny(
        _INVALID_TRANSITION,
        "Submitting a resolution requires an in-progress or pending-vendor ticket.",
    )


def _eval_confirm_resolution(state: TicketState, request: ActionRequest) -> TransitionResult:
    if (
        state.status != TicketStatus.PENDING_USER
        or state.pending_user_reason != PendingUserReason.RESOLUTION_CONFIRMATION
    ):
        return TransitionResult.deny(
            _INVALID_TRANSITION, "Confirming a resolution requires that one was submitted."
        )
    if not _is_requester(state, request):
        return TransitionResult.deny(
            _NOT_REQUESTER, "Only the ticket's requester may confirm a resolution."
        )
    return TransitionResult(
        allowed=True,
        target_status=TicketStatus.RESOLVED,
        resolution_type=ResolutionType.USER_CONFIRMED,
        cycle_effect="NONE",
    )


def _eval_reopen(state: TicketState, request: ActionRequest) -> TransitionResult:
    if state.status != TicketStatus.RESOLVED:
        return TransitionResult.deny(_INVALID_TRANSITION, "Reopening requires a resolved ticket.")
    if not _is_requester(state, request):
        return TransitionResult.deny(_NOT_REQUESTER, "Only the ticket's requester may reopen it.")
    return TransitionResult(allowed=True, target_status=TicketStatus.REOPENED, cycle_effect="NEW")


def _eval_manual_close(state: TicketState, request: ActionRequest) -> TransitionResult:
    if state.status != TicketStatus.RESOLVED:
        return TransitionResult.deny(
            _INVALID_TRANSITION, "Manual close requires a resolved ticket."
        )
    if not _is_requester(state, request):
        return TransitionResult.deny(
            _NOT_REQUESTER, "Only the ticket's requester may manually close it."
        )
    return TransitionResult(
        allowed=True,
        target_status=TicketStatus.CLOSED,
        closure_type=ClosureType.MANUAL_USER,
        cycle_effect="NONE",
    )


def _eval_auto_resolve_no_response(state: TicketState, _request: ActionRequest) -> TransitionResult:
    if (
        state.status != TicketStatus.PENDING_USER
        or state.pending_user_reason != PendingUserReason.INFORMATION_REQUIRED
    ):
        return TransitionResult.deny(
            _INVALID_TRANSITION,
            "Auto-resolve-no-response requires a pending-user/information-required ticket.",
        )
    return TransitionResult(
        allowed=True,
        target_status=TicketStatus.RESOLVED,
        resolution_type=ResolutionType.AUTO_NO_USER_RESPONSE,
        cycle_effect="NONE",
    )


def _eval_auto_resolve_confirmation_timeout(
    state: TicketState, _request: ActionRequest
) -> TransitionResult:
    if (
        state.status != TicketStatus.PENDING_USER
        or state.pending_user_reason != PendingUserReason.RESOLUTION_CONFIRMATION
    ):
        return TransitionResult.deny(
            _INVALID_TRANSITION,
            "Auto-resolve-confirmation-timeout needs a pending-user/resolution-confirmation ticket",
        )
    return TransitionResult(
        allowed=True,
        target_status=TicketStatus.RESOLVED,
        resolution_type=ResolutionType.AUTO_CONFIRMATION_TIMEOUT,
        cycle_effect="NONE",
    )


def _eval_auto_close(state: TicketState, _request: ActionRequest) -> TransitionResult:
    if state.status != TicketStatus.RESOLVED:
        return TransitionResult.deny(_INVALID_TRANSITION, "Auto-close requires a resolved ticket.")
    return TransitionResult(
        allowed=True,
        target_status=TicketStatus.CLOSED,
        closure_type=ClosureType.AUTO_AFTER_7_DAYS,
        cycle_effect="NONE",
    )


_HANDLERS = {
    WorkflowAction.ASSIGN: _eval_assign,
    WorkflowAction.ESCALATE: _eval_escalate,
    WorkflowAction.START: _eval_start,
    WorkflowAction.REQUEST_USER_INFO: _eval_request_user_info,
    WorkflowAction.USER_RESUME: _eval_user_resume,
    WorkflowAction.REQUEST_VENDOR: _eval_request_vendor,
    WorkflowAction.VENDOR_RESPONSE: _eval_vendor_response,
    WorkflowAction.SUBMIT_RESOLUTION: _eval_submit_resolution,
    WorkflowAction.CONFIRM_RESOLUTION: _eval_confirm_resolution,
    WorkflowAction.REOPEN: _eval_reopen,
    WorkflowAction.MANUAL_CLOSE: _eval_manual_close,
    WorkflowAction.AUTO_RESOLVE_NO_RESPONSE: _eval_auto_resolve_no_response,
    WorkflowAction.AUTO_RESOLVE_CONFIRMATION_TIMEOUT: _eval_auto_resolve_confirmation_timeout,
    WorkflowAction.AUTO_CLOSE: _eval_auto_close,
}


def evaluate(state: TicketState, request: ActionRequest) -> TransitionResult:
    """Decide whether ``request.action`` is legal from ``state``.

    CLOSED is checked first and unconditionally, per baseline §4.6: it is
    a business-read-only terminal state for every action, with no
    per-action exception.
    """
    if state.status == TicketStatus.CLOSED:
        return TransitionResult.deny(
            _TICKET_CLOSED, "This ticket is closed and accepts no further actions."
        )
    return _HANDLERS[request.action](state, request)


def available_actions(
    state: TicketState,
    *,
    actor_role: UserRole | None,
    actor_id: int | None,
    actor_vendor_org_id: int | None = None,
) -> set[WorkflowAction]:
    """The subset of user-facing actions this actor could attempt now.

    For WorkflowReadModel (C021) only -- a caller about to actually write
    a change MUST call ``evaluate`` again with the concrete target
    (assignee, vendor org, ...) before committing anything (C016.05).
    """
    found: set[WorkflowAction] = set()
    for action in USER_FACING_ACTIONS:
        request = ActionRequest(
            action=action,
            actor_role=actor_role,
            actor_id=actor_id,
            actor_vendor_org_id=actor_vendor_org_id,
            active_vendor_request_org_id=actor_vendor_org_id
            if state.has_active_vendor_request
            else None,
        )
        if evaluate(state, request).allowed:
            found.add(action)
    return found
