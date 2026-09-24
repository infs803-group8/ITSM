"""Unit tests for app.domains.workflow.service.ManualCloseService (C034).

Fake-repository/audit/deadlines pattern -- same conventions as
test_reopen_service.py, this action's sibling caller of
DeadlineService.enforce_resolved_not_auto_closed. Imports SQLAlchemy
transitively, so syntax-checked only (py_compile), not executed.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.common.request_context import RequestContext
from app.core.errors import ApplicationError
from app.domains.workflow.service import ManualCloseService
from app.domains.workflow.state_machine import TicketStatus

NOW = datetime(2026, 9, 1, 0, 0, 0, tzinfo=UTC)
REQUESTER = RequestContext(user_id=10, role="USER")
OTHER_USER = RequestContext(user_id=11, role="USER")


class WorkflowRepositoryFake:
    def __init__(self, *, ticket_row):
        self.ticket_row = ticket_row
        self.vendor_row = None
        self.applied = None

    def get_ticket_state_row(self, ticket_id):
        return self.ticket_row

    def get_latest_vendor_request(self, ticket_id):
        return self.vendor_row

    def apply_manual_close(self, *, ticket_id, closed_at):
        self.applied = {"ticket_id": ticket_id, "closed_at": closed_at}


class DeadlineFake:
    """Same shape as test_reopen_service.py's -- ManualCloseService is
    DeadlineService.enforce_resolved_not_auto_closed's other named
    caller.
    """

    def __init__(self):
        self.expired = False
        self.calls = []

    def enforce_resolved_not_auto_closed(self, snapshot, *, now):
        self.calls.append({"snapshot": snapshot, "now": now})
        if self.expired:
            raise ApplicationError(
                "TICKET_CLOSED",
                "This ticket was automatically closed; it accepts no further actions.",
                409,
            )


class AuditFake:
    def __init__(self):
        self.events = []
        self._next_id = 12001

    def append_event(self, **kwargs):
        self.events.append(kwargs)
        event_id = self._next_id
        self._next_id += 1
        return event_id


def resolved_ticket_row(**overrides):
    row = {
        "ticket_id": 1,
        "status_code": "RESOLVED",
        "requester_id": 10,
        "assignee_id": 20,
        "category_code": "NETWORK",
        "sla_cycle_no": 1,
        "sla_status_code": "ON_TRACK",
        "sla_deadline": NOW + timedelta(hours=30),
        "pending_user_reason": None,
        "pending_user_deadline": None,
        "resolution_summary": "Replaced the faulty cable.",
        "resolution_type": "USER_CONFIRMED",
        "resolved_at": NOW - timedelta(hours=1),
        "auto_close_at": NOW + timedelta(hours=167),
        "closure_type": None,
        "closed_at": None,
        "last_resolved_assignee_id": 20,
        "assignee_role_code": "ENGINEER_TIER1",
    }
    row.update(overrides)
    return row


def manual_close_service(ticket_row, *, expired=False):
    service = ManualCloseService(None)
    service.repository = WorkflowRepositoryFake(ticket_row=ticket_row)
    service.audit = AuditFake()
    service.deadlines = DeadlineFake()
    service.deadlines.expired = expired
    return service


def test_the_requester_can_manually_close_a_resolved_ticket():
    service = manual_close_service(resolved_ticket_row())
    outcome = service.manual_close(ticket_id=1, actor=REQUESTER, reason=None, now=NOW)

    assert outcome.status is TicketStatus.CLOSED
    assert service.repository.applied == {"ticket_id": 1, "closed_at": NOW}
    assert len(service.audit.events) == 1
    event = service.audit.events[0]
    assert event["event_type"].value == "TICKET_CLOSED_MANUAL"
    assert event["scope"].value == "USER_VISIBLE"
    assert event["metadata"] is None
    assert outcome.event_id == 12001


def test_an_optional_reason_is_recorded_in_the_event_metadata():
    service = manual_close_service(resolved_ticket_row())
    service.manual_close(ticket_id=1, actor=REQUESTER, reason="No longer an issue.", now=NOW)
    assert service.audit.events[0]["metadata"] == {"reason": "No longer an issue."}


def test_an_already_auto_closed_ticket_reports_ticket_closed_instead_of_closing_again():
    service = manual_close_service(resolved_ticket_row(), expired=True)
    with pytest.raises(ApplicationError) as excinfo:
        service.manual_close(ticket_id=1, actor=REQUESTER, reason=None, now=NOW)
    assert excinfo.value.code == "TICKET_CLOSED"
    assert service.repository.applied is None
    assert len(service.deadlines.calls) == 1


def test_a_different_user_cannot_close():
    service = manual_close_service(resolved_ticket_row())
    with pytest.raises(ApplicationError) as excinfo:
        service.manual_close(ticket_id=1, actor=OTHER_USER, reason=None, now=NOW)
    assert excinfo.value.code == "DATA_SCOPE_DENIED"
    assert service.repository.applied is None


def test_a_ticket_that_is_not_resolved_is_rejected():
    row = resolved_ticket_row(
        status_code="IN_PROGRESS",
        resolution_summary=None,
        resolution_type=None,
        resolved_at=None,
        auto_close_at=None,
    )
    service = manual_close_service(row)
    with pytest.raises(ApplicationError) as excinfo:
        service.manual_close(ticket_id=1, actor=REQUESTER, reason=None, now=NOW)
    assert excinfo.value.code == "INVALID_STATUS_TRANSITION"
    assert service.repository.applied is None


def test_an_already_closed_ticket_is_rejected():
    row = resolved_ticket_row(status_code="CLOSED")
    service = manual_close_service(row)
    with pytest.raises(ApplicationError) as excinfo:
        service.manual_close(ticket_id=1, actor=REQUESTER, reason=None, now=NOW)
    assert excinfo.value.code == "TICKET_CLOSED"


def test_missing_ticket_raises_404():
    service = manual_close_service(None)
    with pytest.raises(ApplicationError) as excinfo:
        service.manual_close(ticket_id=1, actor=REQUESTER, reason=None, now=NOW)
    assert excinfo.value.status_code == 404
