"""Unit tests for app.domains.workflow.service (C025 onward).

Fake-repository/audit pattern. Imports SQLAlchemy transitively (via
action_engine -> repository), so syntax-checked only (py_compile), not
executed, in an environment without pip access -- same convention as
every other DB-touching service test in this codebase.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.common.request_context import RequestContext
from app.core.errors import ApplicationError
from app.domains.workflow.service import StartTicketService
from app.domains.workflow.state_machine import TicketStatus

NOW = datetime(2026, 9, 1, 0, 0, 0, tzinfo=UTC)
ASSIGNEE = RequestContext(user_id=20, role="ENGINEER_TIER1")
OTHER_ENGINEER = RequestContext(user_id=21, role="ENGINEER_TIER1")


class RepositoryFake:
    def __init__(self, *, ticket_row, vendor_row=None):
        self.ticket_row = ticket_row
        self.vendor_row = vendor_row
        self.applied_status = None

    def get_ticket_state_row(self, ticket_id):
        return self.ticket_row

    def get_latest_vendor_request(self, ticket_id):
        return self.vendor_row

    def apply_status_change(self, *, ticket_id, status_code):
        self.applied_status = status_code


class AuditFake:
    def __init__(self):
        self.events = []

    def append_event(self, **kwargs):
        self.events.append(kwargs)
        return 5001


def assigned_ticket_row(**overrides):
    row = {
        "ticket_id": 1,
        "status_code": "ASSIGNED",
        "requester_id": 10,
        "assignee_id": 20,
        "category_code": "NETWORK",
        "sla_cycle_no": 1,
        "sla_status_code": "ON_TRACK",
        "sla_deadline": NOW + timedelta(hours=48),
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


def start_service(ticket_row):
    service = StartTicketService(None)
    service.repository = RepositoryFake(ticket_row=ticket_row)
    service.audit = AuditFake()
    return service


def test_current_assignee_can_start_an_assigned_ticket():
    service = start_service(assigned_ticket_row())
    outcome = service.start(ticket_id=1, actor=ASSIGNEE, now=NOW)
    assert outcome.status is TicketStatus.IN_PROGRESS
    assert outcome.event_id == 5001
    assert service.repository.applied_status == "IN_PROGRESS"
    assert service.audit.events[0]["event_type"].value == "HANDLING_STARTED"


def test_current_assignee_can_start_a_reopened_ticket_with_an_assignee():
    row = assigned_ticket_row(status_code="REOPENED")
    service = start_service(row)
    outcome = service.start(ticket_id=1, actor=ASSIGNEE, now=NOW)
    assert outcome.status is TicketStatus.IN_PROGRESS


def test_a_different_engineer_cannot_start_it():
    service = start_service(assigned_ticket_row())
    with pytest.raises(ApplicationError) as excinfo:
        service.start(ticket_id=1, actor=OTHER_ENGINEER, now=NOW)
    assert excinfo.value.code == "DATA_SCOPE_DENIED"
    assert excinfo.value.status_code == 403


def test_reopened_ticket_with_no_assignee_cannot_be_started_by_anyone():
    row = assigned_ticket_row(status_code="REOPENED", assignee_id=None, assignee_role_code=None)
    service = start_service(row)
    with pytest.raises(ApplicationError):
        service.start(ticket_id=1, actor=ASSIGNEE, now=NOW)


def test_starting_an_already_in_progress_ticket_is_rejected():
    row = assigned_ticket_row(status_code="IN_PROGRESS")
    service = start_service(row)
    with pytest.raises(ApplicationError) as excinfo:
        service.start(ticket_id=1, actor=ASSIGNEE, now=NOW)
    assert excinfo.value.code == "INVALID_STATUS_TRANSITION"
    assert excinfo.value.status_code == 409


def test_starting_a_closed_ticket_is_rejected():
    row = assigned_ticket_row(status_code="CLOSED")
    service = start_service(row)
    with pytest.raises(ApplicationError) as excinfo:
        service.start(ticket_id=1, actor=ASSIGNEE, now=NOW)
    assert excinfo.value.code == "TICKET_CLOSED"


def test_missing_ticket_raises_404():
    service = start_service(None)
    with pytest.raises(ApplicationError) as excinfo:
        service.start(ticket_id=1, actor=ASSIGNEE, now=NOW)
    assert excinfo.value.status_code == 404


def test_start_never_touches_sla_cycle_fields():
    """C025.03: apply_status_change is the ONLY repository write Start
    performs -- there is no method on the fake for touching sla_cycle_no/
    sla_started_at/sla_deadline, so calling one would raise AttributeError
    and fail this test.
    """
    service = start_service(assigned_ticket_row())
    service.start(ticket_id=1, actor=ASSIGNEE, now=NOW)
    assert service.repository.applied_status == "IN_PROGRESS"


# ---------------------------------------------------------------------------
# ITSM check report P1: MySQL DATETIME comes back naive through raw SQL, while
# ``now`` is UTC-aware. The overdue judgment must normalise before comparing.
# ---------------------------------------------------------------------------

NAIVE_NOW = NOW.replace(tzinfo=None)


def test_start_accepts_a_naive_future_sla_deadline_from_mysql():
    row = assigned_ticket_row(sla_deadline=NAIVE_NOW + timedelta(hours=48))
    service = start_service(row)
    outcome = service.start(ticket_id=1, actor=ASSIGNEE, now=NOW)
    assert outcome.status is TicketStatus.IN_PROGRESS


def test_lock_ticket_state_treats_naive_future_deadline_as_on_track():
    from app.domains.workflow.action_engine import lock_ticket_state
    from app.domains.workflow.state_machine import SlaStatus

    repository = RepositoryFake(
        ticket_row=assigned_ticket_row(sla_deadline=NAIVE_NOW + timedelta(hours=1))
    )
    locked = lock_ticket_state(repository, ticket_id=1, now=NOW)
    assert locked.state.sla_status is SlaStatus.ON_TRACK


def test_lock_ticket_state_treats_naive_past_deadline_as_overdue():
    from app.domains.workflow.action_engine import lock_ticket_state
    from app.domains.workflow.state_machine import SlaStatus

    repository = RepositoryFake(
        ticket_row=assigned_ticket_row(sla_deadline=NAIVE_NOW - timedelta(hours=1))
    )
    locked = lock_ticket_state(repository, ticket_id=1, now=NOW)
    assert locked.state.sla_status is SlaStatus.OVERDUE


def test_lock_ticket_state_with_no_deadline_keeps_stored_status():
    from app.domains.workflow.action_engine import lock_ticket_state
    from app.domains.workflow.state_machine import SlaStatus

    repository = RepositoryFake(ticket_row=assigned_ticket_row(sla_deadline=None))
    locked = lock_ticket_state(repository, ticket_id=1, now=NOW)
    assert locked.state.sla_status is SlaStatus.ON_TRACK
