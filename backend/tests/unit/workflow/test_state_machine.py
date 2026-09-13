import pytest

from app.core.enums import TicketStatus, UserRole
from app.domains.workflow.state_machine import (
    SYSTEM_ONLY_ACTIONS,
    ActionRequest,
    ClosureType,
    PendingUserReason,
    ResolutionType,
    SlaStatus,
    TicketState,
    WorkflowAction,
    available_actions,
    evaluate,
)

REQUESTER = 1001
TIER1 = 2001
TIER2 = 2002
VENDOR_ORG = 7


def state(**overrides) -> TicketState:
    values = dict(
        status=TicketStatus.IN_PROGRESS,
        assignee_id=TIER1,
        assignee_role=UserRole.ENGINEER_TIER1,
        requester_id=REQUESTER,
        sla_status=SlaStatus.ON_TRACK,
        pending_user_reason=None,
        has_active_vendor_request=False,
    )
    values.update(overrides)
    return TicketState(**values)


def request(action: WorkflowAction, **overrides) -> ActionRequest:
    values = dict(actor_role=None, actor_id=None)
    values.update(overrides)
    return ActionRequest(action=action, **values)


# --- CLOSED is a universal terminal state ----------------------------------


@pytest.mark.parametrize("action", list(WorkflowAction))
def test_every_action_is_denied_on_a_closed_ticket(action):
    closed = state(status=TicketStatus.CLOSED)
    result = evaluate(closed, request(action, actor_role=UserRole.SERVICE_DESK_MANAGER, actor_id=99))
    assert result.allowed is False
    assert result.denial_code == "TICKET_CLOSED"


# --- ASSIGN (API-21 matrix, baseline §4.5) ---------------------------------


def test_assign_unassigned_not_overdue_allows_either_tier():
    unassigned = state(status=TicketStatus.UNASSIGNED, assignee_id=None, assignee_role=None)
    result = evaluate(
        unassigned,
        request(
            WorkflowAction.ASSIGN,
            actor_role=UserRole.SERVICE_DESK_MANAGER,
            actor_id=99,
            target_assignee_role=UserRole.ENGINEER_TIER1,
            target_assignee_available=True,
        ),
    )
    assert result.allowed
    assert result.target_status == TicketStatus.ASSIGNED
    assert result.cycle_effect == "KEEP"


def test_assign_unassigned_overdue_rejects_tier1_target():
    unassigned_overdue = state(
        status=TicketStatus.UNASSIGNED,
        assignee_id=None,
        assignee_role=None,
        sla_status=SlaStatus.OVERDUE,
    )
    result = evaluate(
        unassigned_overdue,
        request(
            WorkflowAction.ASSIGN,
            actor_role=UserRole.SERVICE_DESK_MANAGER,
            actor_id=99,
            target_assignee_role=UserRole.ENGINEER_TIER1,
            target_assignee_available=True,
        ),
    )
    assert result.allowed is False
    assert result.denial_code == "TARGET_ASSIGNEE_NOT_ELIGIBLE"


def test_assign_unassigned_overdue_allows_tier2_target():
    unassigned_overdue = state(
        status=TicketStatus.UNASSIGNED,
        assignee_id=None,
        assignee_role=None,
        sla_status=SlaStatus.OVERDUE,
    )
    result = evaluate(
        unassigned_overdue,
        request(
            WorkflowAction.ASSIGN,
            actor_role=UserRole.SERVICE_DESK_MANAGER,
            actor_id=99,
            target_assignee_role=UserRole.ENGINEER_TIER2,
            target_assignee_available=True,
        ),
    )
    assert result.allowed


def test_assign_only_a_manager_may_act():
    unassigned = state(status=TicketStatus.UNASSIGNED, assignee_id=None, assignee_role=None)
    result = evaluate(
        unassigned,
        request(
            WorkflowAction.ASSIGN,
            actor_role=UserRole.ENGINEER_TIER2,
            actor_id=TIER2,
            target_assignee_role=UserRole.ENGINEER_TIER1,
            target_assignee_available=True,
        ),
    )
    assert result.allowed is False
    assert result.denial_code == "ROLE_NOT_PERMITTED"


def test_assign_reassign_overdue_in_progress_requires_tier2():
    overdue_in_progress = state(sla_status=SlaStatus.OVERDUE)
    denied = evaluate(
        overdue_in_progress,
        request(
            WorkflowAction.ASSIGN,
            actor_role=UserRole.SERVICE_DESK_MANAGER,
            actor_id=99,
            target_assignee_role=UserRole.ENGINEER_TIER1,
            target_assignee_available=True,
        ),
    )
    assert denied.allowed is False
    allowed = evaluate(
        overdue_in_progress,
        request(
            WorkflowAction.ASSIGN,
            actor_role=UserRole.SERVICE_DESK_MANAGER,
            actor_id=99,
            target_assignee_role=UserRole.ENGINEER_TIER2,
            target_assignee_available=True,
        ),
    )
    assert allowed.allowed


def test_assign_not_overdue_assigned_ticket_is_rejected():
    assigned_on_track = state(status=TicketStatus.ASSIGNED, sla_status=SlaStatus.ON_TRACK)
    result = evaluate(
        assigned_on_track,
        request(
            WorkflowAction.ASSIGN,
            actor_role=UserRole.SERVICE_DESK_MANAGER,
            actor_id=99,
            target_assignee_role=UserRole.ENGINEER_TIER2,
            target_assignee_available=True,
        ),
    )
    assert result.allowed is False
    assert result.denial_code == "INVALID_STATUS_TRANSITION"


def test_assign_pending_user_from_tier1_assignee_allows_either_tier():
    pending = state(
        status=TicketStatus.PENDING_USER,
        pending_user_reason=PendingUserReason.INFORMATION_REQUIRED,
    )
    result = evaluate(
        pending,
        request(
            WorkflowAction.ASSIGN,
            actor_role=UserRole.SERVICE_DESK_MANAGER,
            actor_id=99,
            target_assignee_role=UserRole.ENGINEER_TIER1,
            target_assignee_available=True,
        ),
    )
    assert result.allowed
    assert result.target_status == TicketStatus.PENDING_USER
    assert result.target_pending_user_reason == PendingUserReason.INFORMATION_REQUIRED


def test_assign_pending_user_from_tier2_assignee_requires_tier2_target():
    pending = state(
        status=TicketStatus.PENDING_USER,
        assignee_id=TIER2,
        assignee_role=UserRole.ENGINEER_TIER2,
        pending_user_reason=PendingUserReason.RESOLUTION_CONFIRMATION,
    )
    denied = evaluate(
        pending,
        request(
            WorkflowAction.ASSIGN,
            actor_role=UserRole.SERVICE_DESK_MANAGER,
            actor_id=99,
            target_assignee_role=UserRole.ENGINEER_TIER1,
            target_assignee_available=True,
        ),
    )
    assert denied.allowed is False


def test_assign_pending_vendor_requires_overdue_and_active_request():
    pending_vendor = state(
        status=TicketStatus.PENDING_VENDOR,
        assignee_id=TIER2,
        assignee_role=UserRole.ENGINEER_TIER2,
        sla_status=SlaStatus.OVERDUE,
        has_active_vendor_request=True,
    )
    result = evaluate(
        pending_vendor,
        request(
            WorkflowAction.ASSIGN,
            actor_role=UserRole.SERVICE_DESK_MANAGER,
            actor_id=99,
            target_assignee_role=UserRole.ENGINEER_TIER2,
            target_assignee_available=True,
        ),
    )
    assert result.allowed
    assert result.target_status == TicketStatus.PENDING_VENDOR


def test_assign_pending_vendor_without_active_request_is_rejected():
    pending_vendor = state(
        status=TicketStatus.PENDING_VENDOR,
        assignee_id=TIER2,
        assignee_role=UserRole.ENGINEER_TIER2,
        sla_status=SlaStatus.OVERDUE,
        has_active_vendor_request=False,
    )
    result = evaluate(
        pending_vendor,
        request(
            WorkflowAction.ASSIGN,
            actor_role=UserRole.SERVICE_DESK_MANAGER,
            actor_id=99,
            target_assignee_role=UserRole.ENGINEER_TIER2,
            target_assignee_available=True,
        ),
    )
    assert result.allowed is False


def test_assign_reopened_with_unavailable_original_assignee():
    reopened = state(status=TicketStatus.REOPENED, assignee_id=None, assignee_role=None)
    result = evaluate(
        reopened,
        request(
            WorkflowAction.ASSIGN,
            actor_role=UserRole.SERVICE_DESK_MANAGER,
            actor_id=99,
            target_assignee_role=UserRole.ENGINEER_TIER1,
            target_assignee_available=True,
        ),
    )
    assert result.allowed


def test_assign_without_a_concrete_target_reports_the_action_as_available():
    unassigned = state(status=TicketStatus.UNASSIGNED, assignee_id=None, assignee_role=None)
    result = evaluate(
        unassigned, request(WorkflowAction.ASSIGN, actor_role=UserRole.SERVICE_DESK_MANAGER, actor_id=99)
    )
    assert result.allowed


# --- ESCALATE ----------------------------------------------------------------


def test_escalate_by_current_tier1_assignee_succeeds():
    result = evaluate(
        state(),
        request(
            WorkflowAction.ESCALATE,
            actor_role=UserRole.ENGINEER_TIER1,
            actor_id=TIER1,
            target_assignee_role=UserRole.ENGINEER_TIER2,
        ),
    )
    assert result.allowed
    assert result.target_status == TicketStatus.ASSIGNED
    assert result.cycle_effect == "KEEP"


def test_escalate_by_someone_other_than_the_assignee_is_denied():
    result = evaluate(
        state(),
        request(WorkflowAction.ESCALATE, actor_role=UserRole.ENGINEER_TIER1, actor_id=TIER1 + 1),
    )
    assert result.allowed is False
    assert result.denial_code == "NOT_TICKET_ASSIGNEE"


def test_escalate_cannot_target_another_tier1():
    result = evaluate(
        state(),
        request(
            WorkflowAction.ESCALATE,
            actor_role=UserRole.ENGINEER_TIER1,
            actor_id=TIER1,
            target_assignee_role=UserRole.ENGINEER_TIER1,
        ),
    )
    assert result.allowed is False


# --- START -------------------------------------------------------------------


@pytest.mark.parametrize("status", [TicketStatus.ASSIGNED, TicketStatus.REOPENED])
def test_start_by_the_current_assignee_succeeds(status):
    result = evaluate(
        state(status=status),
        request(WorkflowAction.START, actor_role=UserRole.ENGINEER_TIER1, actor_id=TIER1),
    )
    assert result.allowed
    assert result.target_status == TicketStatus.IN_PROGRESS


def test_start_from_in_progress_is_rejected():
    result = evaluate(
        state(status=TicketStatus.IN_PROGRESS),
        request(WorkflowAction.START, actor_role=UserRole.ENGINEER_TIER1, actor_id=TIER1),
    )
    assert result.allowed is False
    assert result.denial_code == "INVALID_STATUS_TRANSITION"


def test_start_by_a_non_assignee_is_rejected():
    result = evaluate(
        state(status=TicketStatus.ASSIGNED),
        request(WorkflowAction.START, actor_role=UserRole.ENGINEER_TIER1, actor_id=TIER1 + 1),
    )
    assert result.allowed is False
    assert result.denial_code == "NOT_TICKET_ASSIGNEE"


# --- REQUEST_USER_INFO / USER_RESUME -----------------------------------------


def test_request_user_info_pauses_the_cycle():
    result = evaluate(
        state(),
        request(WorkflowAction.REQUEST_USER_INFO, actor_role=UserRole.ENGINEER_TIER1, actor_id=TIER1),
    )
    assert result.allowed
    assert result.target_status == TicketStatus.PENDING_USER
    assert result.target_pending_user_reason == PendingUserReason.INFORMATION_REQUIRED
    assert result.cycle_effect == "PAUSE"


@pytest.mark.parametrize(
    "reason", [PendingUserReason.INFORMATION_REQUIRED, PendingUserReason.RESOLUTION_CONFIRMATION]
)
def test_user_resume_covers_both_resume_and_issue_persists(reason):
    pending = state(status=TicketStatus.PENDING_USER, pending_user_reason=reason)
    result = evaluate(
        pending, request(WorkflowAction.USER_RESUME, actor_role=UserRole.USER, actor_id=REQUESTER)
    )
    assert result.allowed
    assert result.target_status == TicketStatus.IN_PROGRESS
    assert result.cycle_effect == "NEW"


def test_user_resume_by_someone_other_than_the_requester_is_denied():
    pending = state(status=TicketStatus.PENDING_USER, pending_user_reason=PendingUserReason.INFORMATION_REQUIRED)
    result = evaluate(
        pending, request(WorkflowAction.USER_RESUME, actor_role=UserRole.USER, actor_id=REQUESTER + 1)
    )
    assert result.allowed is False
    assert result.denial_code == "NOT_TICKET_REQUESTER"


# --- REQUEST_VENDOR / VENDOR_RESPONSE ----------------------------------------


def test_request_vendor_by_current_tier2_assignee_succeeds():
    tier2_ticket = state(assignee_id=TIER2, assignee_role=UserRole.ENGINEER_TIER2)
    result = evaluate(
        tier2_ticket,
        request(WorkflowAction.REQUEST_VENDOR, actor_role=UserRole.ENGINEER_TIER2, actor_id=TIER2),
    )
    assert result.allowed
    assert result.target_status == TicketStatus.PENDING_VENDOR
    assert result.vendor_request_effect == "CREATE_ACTIVE"


def test_request_vendor_by_tier1_is_denied():
    result = evaluate(
        state(),
        request(WorkflowAction.REQUEST_VENDOR, actor_role=UserRole.ENGINEER_TIER1, actor_id=TIER1),
    )
    assert result.allowed is False


def test_request_vendor_when_one_is_already_active_is_denied():
    tier2_ticket = state(
        assignee_id=TIER2, assignee_role=UserRole.ENGINEER_TIER2, has_active_vendor_request=True
    )
    result = evaluate(
        tier2_ticket,
        request(WorkflowAction.REQUEST_VENDOR, actor_role=UserRole.ENGINEER_TIER2, actor_id=TIER2),
    )
    assert result.allowed is False
    assert result.denial_code == "VENDOR_REQUEST_ALREADY_ACTIVE"


def test_vendor_response_from_the_owning_organisation_succeeds():
    pending_vendor = state(
        status=TicketStatus.PENDING_VENDOR,
        assignee_id=TIER2,
        assignee_role=UserRole.ENGINEER_TIER2,
        has_active_vendor_request=True,
    )
    result = evaluate(
        pending_vendor,
        request(
            WorkflowAction.VENDOR_RESPONSE,
            actor_role=UserRole.EXTERNAL_VENDOR,
            actor_id=5001,
            actor_vendor_org_id=VENDOR_ORG,
            active_vendor_request_org_id=VENDOR_ORG,
        ),
    )
    assert result.allowed
    assert result.target_status == TicketStatus.IN_PROGRESS
    assert result.vendor_request_effect == "MARK_RESPONDED"


def test_vendor_response_from_a_different_organisation_is_denied():
    pending_vendor = state(
        status=TicketStatus.PENDING_VENDOR,
        assignee_id=TIER2,
        assignee_role=UserRole.ENGINEER_TIER2,
        has_active_vendor_request=True,
    )
    result = evaluate(
        pending_vendor,
        request(
            WorkflowAction.VENDOR_RESPONSE,
            actor_role=UserRole.EXTERNAL_VENDOR,
            actor_id=5001,
            actor_vendor_org_id=VENDOR_ORG + 1,
            active_vendor_request_org_id=VENDOR_ORG,
        ),
    )
    assert result.allowed is False
    assert result.denial_code == "VENDOR_ORG_MISMATCH"


def test_vendor_response_without_an_active_request_is_denied():
    pending_vendor = state(
        status=TicketStatus.PENDING_VENDOR,
        assignee_id=TIER2,
        assignee_role=UserRole.ENGINEER_TIER2,
        has_active_vendor_request=False,
    )
    result = evaluate(
        pending_vendor,
        request(
            WorkflowAction.VENDOR_RESPONSE,
            actor_role=UserRole.EXTERNAL_VENDOR,
            actor_id=5001,
            actor_vendor_org_id=VENDOR_ORG,
        ),
    )
    assert result.allowed is False
    assert result.denial_code == "NO_ACTIVE_VENDOR_REQUEST"


# --- SUBMIT_RESOLUTION / CONFIRM_RESOLUTION -----------------------------------


def test_submit_resolution_from_in_progress_succeeds():
    result = evaluate(
        state(),
        request(WorkflowAction.SUBMIT_RESOLUTION, actor_role=UserRole.ENGINEER_TIER1, actor_id=TIER1),
    )
    assert result.allowed
    assert result.target_status == TicketStatus.PENDING_USER
    assert result.target_pending_user_reason == PendingUserReason.RESOLUTION_CONFIRMATION
    assert result.vendor_request_effect is None


def test_submit_resolution_from_pending_vendor_cancels_the_active_request():
    pending_vendor = state(
        status=TicketStatus.PENDING_VENDOR,
        assignee_id=TIER2,
        assignee_role=UserRole.ENGINEER_TIER2,
        has_active_vendor_request=True,
    )
    result = evaluate(
        pending_vendor,
        request(WorkflowAction.SUBMIT_RESOLUTION, actor_role=UserRole.ENGINEER_TIER2, actor_id=TIER2),
    )
    assert result.allowed
    assert result.vendor_request_effect == "CANCEL_ACTIVE"


def test_confirm_resolution_by_the_requester_succeeds():
    pending = state(status=TicketStatus.PENDING_USER, pending_user_reason=PendingUserReason.RESOLUTION_CONFIRMATION)
    result = evaluate(
        pending, request(WorkflowAction.CONFIRM_RESOLUTION, actor_role=UserRole.USER, actor_id=REQUESTER)
    )
    assert result.allowed
    assert result.target_status == TicketStatus.RESOLVED
    assert result.resolution_type == ResolutionType.USER_CONFIRMED


def test_confirm_resolution_wrong_pending_reason_is_denied():
    pending = state(status=TicketStatus.PENDING_USER, pending_user_reason=PendingUserReason.INFORMATION_REQUIRED)
    result = evaluate(
        pending, request(WorkflowAction.CONFIRM_RESOLUTION, actor_role=UserRole.USER, actor_id=REQUESTER)
    )
    assert result.allowed is False


# --- REOPEN / MANUAL_CLOSE / AUTO_* -------------------------------------------


def test_reopen_by_requester_starts_a_new_cycle():
    resolved = state(status=TicketStatus.RESOLVED)
    result = evaluate(resolved, request(WorkflowAction.REOPEN, actor_role=UserRole.USER, actor_id=REQUESTER))
    assert result.allowed
    assert result.target_status == TicketStatus.REOPENED
    assert result.cycle_effect == "NEW"


def test_manual_close_by_requester_succeeds():
    resolved = state(status=TicketStatus.RESOLVED)
    result = evaluate(resolved, request(WorkflowAction.MANUAL_CLOSE, actor_role=UserRole.USER, actor_id=REQUESTER))
    assert result.allowed
    assert result.closure_type == ClosureType.MANUAL_USER


def test_manual_close_by_a_non_requester_is_denied():
    resolved = state(status=TicketStatus.RESOLVED)
    result = evaluate(
        resolved, request(WorkflowAction.MANUAL_CLOSE, actor_role=UserRole.USER, actor_id=REQUESTER + 1)
    )
    assert result.allowed is False
    assert result.denial_code == "NOT_TICKET_REQUESTER"


def test_auto_resolve_no_response_requires_information_required_reason():
    pending = state(status=TicketStatus.PENDING_USER, pending_user_reason=PendingUserReason.INFORMATION_REQUIRED)
    result = evaluate(pending, request(WorkflowAction.AUTO_RESOLVE_NO_RESPONSE))
    assert result.allowed
    assert result.resolution_type == ResolutionType.AUTO_NO_USER_RESPONSE


def test_auto_resolve_confirmation_timeout_requires_resolution_confirmation_reason():
    pending = state(status=TicketStatus.PENDING_USER, pending_user_reason=PendingUserReason.RESOLUTION_CONFIRMATION)
    result = evaluate(pending, request(WorkflowAction.AUTO_RESOLVE_CONFIRMATION_TIMEOUT))
    assert result.allowed
    assert result.resolution_type == ResolutionType.AUTO_CONFIRMATION_TIMEOUT


def test_auto_close_requires_resolved_state():
    resolved = state(status=TicketStatus.RESOLVED)
    result = evaluate(resolved, request(WorkflowAction.AUTO_CLOSE))
    assert result.allowed
    assert result.closure_type == ClosureType.AUTO_AFTER_7_DAYS


def test_auto_close_from_the_wrong_state_is_denied():
    result = evaluate(state(status=TicketStatus.IN_PROGRESS), request(WorkflowAction.AUTO_CLOSE))
    assert result.allowed is False


# --- available_actions ---------------------------------------------------


def test_available_actions_never_includes_system_only_actions():
    resolved = state(status=TicketStatus.RESOLVED)
    actions = available_actions(resolved, actor_role=UserRole.USER, actor_id=REQUESTER)
    assert actions.isdisjoint(SYSTEM_ONLY_ACTIONS)


def test_available_actions_for_the_requester_on_a_resolved_ticket():
    resolved = state(status=TicketStatus.RESOLVED)
    actions = available_actions(resolved, actor_role=UserRole.USER, actor_id=REQUESTER)
    assert actions == {WorkflowAction.REOPEN, WorkflowAction.MANUAL_CLOSE}


def test_available_actions_for_the_tier1_assignee_on_an_in_progress_ticket():
    actions = available_actions(state(), actor_role=UserRole.ENGINEER_TIER1, actor_id=TIER1)
    assert actions == {
        WorkflowAction.ESCALATE,
        WorkflowAction.REQUEST_USER_INFO,
        WorkflowAction.SUBMIT_RESOLUTION,
    }


def test_available_actions_for_an_unrelated_user_on_a_closed_ticket_is_empty():
    closed = state(status=TicketStatus.CLOSED)
    assert available_actions(closed, actor_role=UserRole.USER, actor_id=999) == set()
