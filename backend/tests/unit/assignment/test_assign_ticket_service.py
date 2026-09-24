"""Unit tests for app.domains.assignment.service.AssignTicketService (C024).

Fake-repository/audit pattern, same as the rest of this codebase's
DB-touching service tests. Imports SQLAlchemy transitively (via
app.domains.workflow.state_machine's siblings), so syntax-checked only
(py_compile), not executed, in an environment without pip access.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.common.request_context import RequestContext
from app.core.errors import ApplicationError
from app.domains.assignment.service import AssignTicketService
from app.domains.workflow.state_machine import TicketStatus

NOW = datetime(2026, 9, 1, 0, 0, 0, tzinfo=UTC)
MANAGER = RequestContext(user_id=1, role="SERVICE_DESK_MANAGER")
ENGINEER = RequestContext(user_id=2, role="ENGINEER_TIER1")


class RepositoryFake:
    def __init__(self, *, ticket_row, target_row, active_vendor_org_id=None):
        self.ticket_row = ticket_row
        self.target_row = target_row
        self.active_vendor_org_id = active_vendor_org_id
        self.applied = None

    def get_ticket_snapshot_for_assign(self, ticket_id):
        return self.ticket_row

    def get_target_engineer(self, user_id, category_code):
        return self.target_row

    def get_active_vendor_request_org(self, ticket_id):
        return self.active_vendor_org_id

    def apply_assignment(self, *, ticket_id, status_code, assignee_id):
        self.applied = {
            "ticket_id": ticket_id,
            "status_code": status_code,
            "assignee_id": assignee_id,
        }


class AuditFake:
    def __init__(self):
        self.events = []

    def append_event(self, **kwargs):
        self.events.append(kwargs)
        return 9001


def service_with(ticket_row, target_row, active_vendor_org_id=None):
    service = AssignTicketService(None)
    service.repository = RepositoryFake(
        ticket_row=ticket_row, target_row=target_row, active_vendor_org_id=active_vendor_org_id
    )
    service.audit = AuditFake()
    return service


def unassigned_ticket_row(**overrides):
    row = {
        "ticket_id": 1,
        "status_code": "UNASSIGNED",
        "requester_id": 10,
        "assignee_id": None,
        "category_code": "NETWORK",
        "sla_status_code": "ON_TRACK",
        "sla_deadline": NOW + timedelta(hours=48),
        "pending_user_reason": None,
        "assignee_role_code": None,
    }
    row.update(overrides)
    return row


def eligible_tier1_row(**overrides):
    row = {
        "user_id": 20,
        "role_code": "ENGINEER_TIER1",
        "is_active": 1,
        "is_available": 1,
        "has_skill": 1,
    }
    row.update(overrides)
    return row


def test_assigning_an_unassigned_ticket_to_an_eligible_tier1_succeeds():
    service = service_with(unassigned_ticket_row(), eligible_tier1_row())
    outcome = service.assign_ticket(
        ticket_id=1, actor=MANAGER, assignee_id=20, reason=None, now=NOW
    )
    assert outcome.status is TicketStatus.ASSIGNED
    assert outcome.event_id == 9001
    assert service.repository.applied == {
        "ticket_id": 1,
        "status_code": "ASSIGNED",
        "assignee_id": 20,
    }
    assert service.audit.events[0]["event_type"].value == "ASSIGNED"


def test_reassigning_writes_a_reassigned_event_not_assigned():
    # Baseline Sec 4.5: ASSIGNED/IN_PROGRESS only accepts Manager
    # reassignment while OVERDUE, and only onto a Tier 2 target.
    row = unassigned_ticket_row(
        status_code="ASSIGNED",
        assignee_id=99,
        assignee_role_code="ENGINEER_TIER1",
        sla_status_code="OVERDUE",
    )
    service = service_with(row, eligible_tier1_row(role_code="ENGINEER_TIER2"))
    service.assign_ticket(ticket_id=1, actor=MANAGER, assignee_id=20, reason="rebalance", now=NOW)
    assert service.audit.events[0]["event_type"].value == "REASSIGNED"
    assert service.audit.events[0]["metadata"]["reason"] == "rebalance"


def test_missing_ticket_raises_404():
    service = service_with(None, eligible_tier1_row())
    with pytest.raises(ApplicationError) as excinfo:
        service.assign_ticket(ticket_id=1, actor=MANAGER, assignee_id=20, reason=None, now=NOW)
    assert excinfo.value.status_code == 404


def test_assigning_to_the_current_assignee_is_rejected():
    row = unassigned_ticket_row(
        status_code="ASSIGNED", assignee_id=20, assignee_role_code="ENGINEER_TIER1"
    )
    service = service_with(row, eligible_tier1_row())
    with pytest.raises(ApplicationError) as excinfo:
        service.assign_ticket(ticket_id=1, actor=MANAGER, assignee_id=20, reason=None, now=NOW)
    assert excinfo.value.code == "ASSIGNEE_NOT_ELIGIBLE"


def test_nonexistent_target_is_rejected():
    service = service_with(unassigned_ticket_row(), None)
    with pytest.raises(ApplicationError) as excinfo:
        service.assign_ticket(ticket_id=1, actor=MANAGER, assignee_id=999, reason=None, now=NOW)
    assert excinfo.value.code == "ASSIGNEE_NOT_ELIGIBLE"
    assert excinfo.value.status_code == 422


def test_target_missing_the_skill_is_rejected():
    service = service_with(unassigned_ticket_row(), eligible_tier1_row(has_skill=0))
    with pytest.raises(ApplicationError) as excinfo:
        service.assign_ticket(ticket_id=1, actor=MANAGER, assignee_id=20, reason=None, now=NOW)
    assert excinfo.value.code == "ASSIGNEE_NOT_ELIGIBLE"


def test_non_manager_actor_is_rejected_with_403():
    service = service_with(unassigned_ticket_row(), eligible_tier1_row())
    with pytest.raises(ApplicationError) as excinfo:
        service.assign_ticket(ticket_id=1, actor=ENGINEER, assignee_id=20, reason=None, now=NOW)
    assert excinfo.value.code == "DATA_SCOPE_DENIED"
    assert excinfo.value.status_code == 403


def test_overdue_unassigned_ticket_requires_a_tier2_target():
    row = unassigned_ticket_row(sla_status_code="ON_TRACK", sla_deadline=NOW - timedelta(hours=1))
    service = service_with(row, eligible_tier1_row())
    with pytest.raises(ApplicationError) as excinfo:
        service.assign_ticket(ticket_id=1, actor=MANAGER, assignee_id=20, reason=None, now=NOW)
    assert excinfo.value.code == "ASSIGNEE_NOT_ELIGIBLE"


def test_overdue_unassigned_ticket_accepts_a_tier2_target_even_before_the_job_marks_it_overdue():
    row = unassigned_ticket_row(sla_status_code="ON_TRACK", sla_deadline=NOW - timedelta(hours=1))
    tier2 = eligible_tier1_row(role_code="ENGINEER_TIER2")
    service = service_with(row, tier2)
    outcome = service.assign_ticket(
        ticket_id=1, actor=MANAGER, assignee_id=20, reason=None, now=NOW
    )
    assert outcome.status is TicketStatus.ASSIGNED


def test_closed_ticket_is_rejected():
    row = unassigned_ticket_row(
        status_code="CLOSED", assignee_id=99, assignee_role_code="ENGINEER_TIER1"
    )
    service = service_with(row, eligible_tier1_row())
    with pytest.raises(ApplicationError) as excinfo:
        service.assign_ticket(ticket_id=1, actor=MANAGER, assignee_id=20, reason=None, now=NOW)
    assert excinfo.value.code == "TICKET_CLOSED"
    assert excinfo.value.status_code == 409


# ITSM check report P1: raw-SQL MySQL DATETIME values are naive.
NAIVE_NOW = NOW.replace(tzinfo=None)


def test_assign_accepts_a_naive_future_sla_deadline_from_mysql():
    row = unassigned_ticket_row(sla_deadline=NAIVE_NOW + timedelta(hours=48))
    service = service_with(row, eligible_tier1_row())
    outcome = service.assign_ticket(
        ticket_id=1, actor=MANAGER, assignee_id=20, reason=None, now=NOW
    )
    assert outcome.status is TicketStatus.ASSIGNED


def test_naive_past_sla_deadline_is_treated_as_overdue_and_requires_tier2():
    row = unassigned_ticket_row(
        sla_status_code="ON_TRACK", sla_deadline=NAIVE_NOW - timedelta(hours=1)
    )
    service = service_with(row, eligible_tier1_row())
    with pytest.raises(ApplicationError) as excinfo:
        service.assign_ticket(ticket_id=1, actor=MANAGER, assignee_id=20, reason=None, now=NOW)
    assert excinfo.value.code == "ASSIGNEE_NOT_ELIGIBLE"
