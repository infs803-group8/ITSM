"""Unit tests for app.domains.workflow.service.EscalateTicketService (C028).

Fake-repository/audit/assignment-repository pattern -- same conventions
as the other C025-C027 service tests. Imports SQLAlchemy transitively,
so syntax-checked only (py_compile), not executed.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.common.request_context import RequestContext
from app.core.errors import ApplicationError
from app.domains.workflow.service import EscalateTicketService
from app.domains.workflow.state_machine import TicketStatus

NOW = datetime(2026, 9, 1, 0, 0, 0, tzinfo=UTC)
TIER1_ASSIGNEE = RequestContext(user_id=20, role="ENGINEER_TIER1")
OTHER_TIER1 = RequestContext(user_id=21, role="ENGINEER_TIER1")
MANAGER = RequestContext(user_id=99, role="SERVICE_DESK_MANAGER")


class WorkflowRepositoryFake:
    def __init__(self, *, ticket_row, vendor_row=None):
        self.ticket_row = ticket_row
        self.vendor_row = vendor_row

    def get_ticket_state_row(self, ticket_id):
        return self.ticket_row

    def get_latest_vendor_request(self, ticket_id):
        return self.vendor_row


class AssignmentRepositoryFake:
    def __init__(self, *, target_row):
        self.target_row = target_row
        self.applied = None

    def get_target_engineer(self, user_id, category_code):
        return self.target_row

    def apply_assignment(self, *, ticket_id, status_code, assignee_id):
        self.applied = {"ticket_id": ticket_id, "status_code": status_code, "assignee_id": assignee_id}


class AuditFake:
    def __init__(self):
        self.events = []
        self._next_id = 4001

    def append_event(self, **kwargs):
        self.events.append(kwargs)
        event_id = self._next_id
        self._next_id += 1
        return event_id


def in_progress_ticket_row(**overrides):
    row = {
        "ticket_id": 1,
        "status_code": "IN_PROGRESS",
        "requester_id": 10,
        "assignee_id": 20,
        "category_code": "NETWORK",
        "sla_cycle_no": 1,
        "sla_status_code": "ON_TRACK",
        "sla_deadline": NOW + timedelta(hours=30),
        "pending_user_reason": None,
        "pending_user_deadline": None,
        "resolution_summary": None,
        "resolution_type": None,
        "resolved_at": None,
        "auto_close_at": None,
        "closure_type": None,
        "closed_at": None,
        "assignee_role_code": "ENGINEER_TIER1",
    }
    row.update(overrides)
    return row


def eligible_tier2_row(**overrides):
    row = {
        "user_id": 30,
        "role_code": "ENGINEER_TIER2",
        "is_active": 1,
        "is_available": 1,
        "has_skill": 1,
    }
    row.update(overrides)
    return row


def escalate_service(ticket_row, target_row):
    service = EscalateTicketService(None)
    service.repository = WorkflowRepositoryFake(ticket_row=ticket_row)
    service.assignment_repository = AssignmentRepositoryFake(target_row=target_row)
    service.audit = AuditFake()
    return service


def test_current_tier1_assignee_can_escalate_to_an_eligible_tier2():
    service = escalate_service(in_progress_ticket_row(), eligible_tier2_row())
    outcome = service.escalate(
        ticket_id=1, actor=TIER1_ASSIGNEE, tier2_assignee_id=30, reason="Needs deeper diagnostics.", now=NOW
    )

    assert outcome.status is TicketStatus.ASSIGNED
    assert service.assignment_repository.applied == {
        "ticket_id": 1,
        "status_code": "ASSIGNED",
        "assignee_id": 30,
    }
    assert len(service.audit.events) == 1
    event = service.audit.events[0]
    assert event["event_type"].value == "REASSIGNED"
    assert event["metadata"] == {
        "from_assignee_id": 20,
        "assignee_id": 30,
        "escalation": True,
        "reason": "Needs deeper diagnostics.",
    }
    assert outcome.event_id == 4001


def test_escalation_without_a_reason_omits_it_from_metadata():
    service = escalate_service(in_progress_ticket_row(), eligible_tier2_row())
    service.escalate(ticket_id=1, actor=TIER1_ASSIGNEE, tier2_assignee_id=30, reason=None, now=NOW)
    assert "reason" not in service.audit.events[0]["metadata"]


def test_a_different_tier1_engineer_cannot_escalate(monkeypatch=None):
    service = escalate_service(in_progress_ticket_row(), eligible_tier2_row())
    with pytest.raises(ApplicationError) as excinfo:
        service.escalate(ticket_id=1, actor=OTHER_TIER1, tier2_assignee_id=30, reason=None, now=NOW)
    assert excinfo.value.code == "DATA_SCOPE_DENIED"
    assert service.assignment_repository.applied is None


def test_a_manager_cannot_call_escalate_directly():
    """Escalate is a Tier 1 self-service handoff, not the Manager's
    Assign/Reassign action (API-21) -- state_machine._eval_escalate
    requires actor_role == ENGINEER_TIER1 specifically.
    """
    service = escalate_service(in_progress_ticket_row(), eligible_tier2_row())
    with pytest.raises(ApplicationError) as excinfo:
        service.escalate(ticket_id=1, actor=MANAGER, tier2_assignee_id=30, reason=None, now=NOW)
    assert excinfo.value.code == "DATA_SCOPE_DENIED"


def test_a_target_that_is_actually_tier1_is_rejected():
    target = eligible_tier2_row(role_code="ENGINEER_TIER1")
    service = escalate_service(in_progress_ticket_row(), target)
    with pytest.raises(ApplicationError) as excinfo:
        service.escalate(ticket_id=1, actor=TIER1_ASSIGNEE, tier2_assignee_id=30, reason=None, now=NOW)
    assert excinfo.value.code == "ASSIGNEE_NOT_ELIGIBLE"
    assert excinfo.value.status_code == 422
    assert service.assignment_repository.applied is None


def test_an_unavailable_tier2_target_is_rejected():
    """C028.02: Active/Available/skill checks are this service's own
    responsibility -- state_machine itself has no concept of
    availability for ESCALATE.
    """
    target = eligible_tier2_row(is_available=0)
    service = escalate_service(in_progress_ticket_row(), target)
    with pytest.raises(ApplicationError) as excinfo:
        service.escalate(ticket_id=1, actor=TIER1_ASSIGNEE, tier2_assignee_id=30, reason=None, now=NOW)
    assert excinfo.value.code == "ASSIGNEE_NOT_ELIGIBLE"


def test_a_target_without_the_ticket_category_skill_is_rejected():
    target = eligible_tier2_row(has_skill=0)
    service = escalate_service(in_progress_ticket_row(), target)
    with pytest.raises(ApplicationError) as excinfo:
        service.escalate(ticket_id=1, actor=TIER1_ASSIGNEE, tier2_assignee_id=30, reason=None, now=NOW)
    assert excinfo.value.code == "ASSIGNEE_NOT_ELIGIBLE"


def test_a_nonexistent_target_is_rejected():
    service = escalate_service(in_progress_ticket_row(), None)
    with pytest.raises(ApplicationError) as excinfo:
        service.escalate(ticket_id=1, actor=TIER1_ASSIGNEE, tier2_assignee_id=999, reason=None, now=NOW)
    assert excinfo.value.code == "ASSIGNEE_NOT_ELIGIBLE"


def test_a_ticket_that_is_not_in_progress_is_rejected():
    row = in_progress_ticket_row(status_code="ASSIGNED")
    service = escalate_service(row, eligible_tier2_row())
    with pytest.raises(ApplicationError) as excinfo:
        service.escalate(ticket_id=1, actor=TIER1_ASSIGNEE, tier2_assignee_id=30, reason=None, now=NOW)
    assert excinfo.value.code == "INVALID_STATUS_TRANSITION"
    assert service.assignment_repository.applied is None


def test_a_closed_ticket_is_rejected():
    row = in_progress_ticket_row(status_code="CLOSED")
    service = escalate_service(row, eligible_tier2_row())
    with pytest.raises(ApplicationError) as excinfo:
        service.escalate(ticket_id=1, actor=TIER1_ASSIGNEE, tier2_assignee_id=30, reason=None, now=NOW)
    assert excinfo.value.code == "TICKET_CLOSED"


def test_missing_ticket_raises_404():
    service = escalate_service(None, eligible_tier2_row())
    with pytest.raises(ApplicationError) as excinfo:
        service.escalate(ticket_id=1, actor=TIER1_ASSIGNEE, tier2_assignee_id=30, reason=None, now=NOW)
    assert excinfo.value.status_code == 404
