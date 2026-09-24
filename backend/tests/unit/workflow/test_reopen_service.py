"""Unit tests for app.domains.workflow.service.ReopenTicketService (C033).

Fake-repository/audit/sla/deadlines/assignment pattern, plus
monkeypatching the module-level ``insert_workflow_comment`` import --
same conventions as test_resume_service.py and test_request_user_info_
service.py. Imports SQLAlchemy transitively, so syntax-checked only
(py_compile), not executed.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.common.request_context import RequestContext
from app.core.errors import ApplicationError
from app.domains.workflow import service as service_module
from app.domains.workflow.service import ReopenTicketService
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

    def apply_reopen(self, *, ticket_id, assignee_id):
        self.applied = {"ticket_id": ticket_id, "assignee_id": assignee_id}


class AssignmentRepositoryFake:
    def __init__(self, *, target_row):
        self.target_row = target_row

    def get_target_engineer(self, user_id, category_code):
        return self.target_row


class AssignmentServiceFake:
    def __init__(self, *, winner_id):
        self.winner_id = winner_id
        self.called_with = None

    def assign_new_ticket(self, *, ticket_id, category_code):
        self.called_with = {"ticket_id": ticket_id, "category_code": category_code}
        return self.winner_id


class SlaFake:
    def __init__(self):
        self.started_cycle = None

    def load_config(self):
        return "CONFIG-SENTINEL"

    def start_new_cycle(self, *, ticket_id, previous_cycle_no, actor_id, now, config):
        self.started_cycle = {
            "ticket_id": ticket_id,
            "previous_cycle_no": previous_cycle_no,
            "actor_id": actor_id,
            "now": now,
            "config": config,
        }


class DeadlineFake:
    """By default the window is still open (never raises); a test that
    needs the expired-window path sets ``self.expired = True``. Same
    fake shape as test_resume_service.py's -- ReopenTicketService is
    deadline_service.py's other named caller of
    ``enforce_resolved_not_auto_closed``.
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
        self._next_id = 11001

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


def eligible_engineer_row(**overrides):
    row = {
        "user_id": 20,
        "role_code": "ENGINEER_TIER1",
        "is_active": 1,
        "is_available": 1,
        "has_skill": 1,
    }
    row.update(overrides)
    return row


def reopen_service(
    ticket_row, *, monkeypatch, target_row=None, winner_id=None, expired=False, comment_id=9101
):
    service = ReopenTicketService(None)
    service.repository = WorkflowRepositoryFake(ticket_row=ticket_row)
    service.assignment_repository = AssignmentRepositoryFake(target_row=target_row)
    service.assignment_service = AssignmentServiceFake(winner_id=winner_id)
    service.audit = AuditFake()
    service.sla = SlaFake()
    service.deadlines = DeadlineFake()
    service.deadlines.expired = expired
    monkeypatch.setattr(
        service_module,
        "insert_workflow_comment",
        lambda database, **kwargs: comment_id,
    )
    return service


def test_the_requester_can_reopen_and_keeps_the_previous_assignee_if_still_eligible(monkeypatch):
    service = reopen_service(
        resolved_ticket_row(), monkeypatch=monkeypatch, target_row=eligible_engineer_row()
    )
    outcome = service.reopen(ticket_id=1, actor=REQUESTER, reason="The issue came back.", now=NOW)

    assert outcome.status is TicketStatus.REOPENED
    assert outcome.assignee_id == 20
    assert outcome.comment_id == 9101
    assert service.repository.applied == {"ticket_id": 1, "assignee_id": 20}
    assert service.assignment_service.called_with is None
    assert service.sla.started_cycle == {
        "ticket_id": 1,
        "previous_cycle_no": 1,
        "actor_id": 10,
        "now": NOW,
        "config": "CONFIG-SENTINEL",
    }
    assert len(service.audit.events) == 2
    comment_event, reopen_event = service.audit.events
    assert comment_event["event_type"].value == "COMMENT_ADDED"
    assert comment_event["comment_id"] == 9101
    assert reopen_event["event_type"].value == "TICKET_REOPENED"
    assert reopen_event.get("comment_id") is None
    assert outcome.event_id == 11002


def test_reopen_falls_back_to_auto_assignment_when_the_previous_assignee_is_no_longer_eligible(
    monkeypatch,
):
    service = reopen_service(
        resolved_ticket_row(),
        monkeypatch=monkeypatch,
        target_row=eligible_engineer_row(is_available=0),
        winner_id=30,
    )
    outcome = service.reopen(ticket_id=1, actor=REQUESTER, reason="x", now=NOW)

    assert outcome.assignee_id == 30
    assert service.assignment_service.called_with == {"ticket_id": 1, "category_code": "NETWORK"}
    assert service.repository.applied == {"ticket_id": 1, "assignee_id": 30}


def test_reopen_succeeds_with_no_assignee_when_nobody_is_eligible(monkeypatch):
    service = reopen_service(
        resolved_ticket_row(last_resolved_assignee_id=None), monkeypatch=monkeypatch, winner_id=None
    )
    outcome = service.reopen(ticket_id=1, actor=REQUESTER, reason="x", now=NOW)

    assert outcome.assignee_id is None
    assert service.repository.applied == {"ticket_id": 1, "assignee_id": None}


def test_an_already_auto_closed_ticket_reports_ticket_closed_instead_of_reopening(monkeypatch):
    """DeadlineService.enforce_resolved_not_auto_closed's own docstring
    names this action (alongside Manual Close) as its two callers -- if
    the 7-day window already passed, the ticket auto-closed and this
    call must report that rather than reopening a ticket that is no
    longer RESOLVED in the database.
    """
    service = reopen_service(resolved_ticket_row(), monkeypatch=monkeypatch, expired=True)
    with pytest.raises(ApplicationError) as excinfo:
        service.reopen(ticket_id=1, actor=REQUESTER, reason="x", now=NOW)
    assert excinfo.value.code == "TICKET_CLOSED"
    assert service.repository.applied is None
    assert len(service.deadlines.calls) == 1


def test_a_different_user_cannot_reopen(monkeypatch):
    service = reopen_service(resolved_ticket_row(), monkeypatch=monkeypatch)
    with pytest.raises(ApplicationError) as excinfo:
        service.reopen(ticket_id=1, actor=OTHER_USER, reason="x", now=NOW)
    assert excinfo.value.code == "DATA_SCOPE_DENIED"
    assert service.repository.applied is None


def test_a_ticket_that_is_not_resolved_is_rejected(monkeypatch):
    row = resolved_ticket_row(
        status_code="IN_PROGRESS",
        resolution_summary=None,
        resolution_type=None,
        resolved_at=None,
        auto_close_at=None,
    )
    service = reopen_service(row, monkeypatch=monkeypatch)
    with pytest.raises(ApplicationError) as excinfo:
        service.reopen(ticket_id=1, actor=REQUESTER, reason="x", now=NOW)
    assert excinfo.value.code == "INVALID_STATUS_TRANSITION"
    assert service.repository.applied is None


def test_a_closed_ticket_is_rejected(monkeypatch):
    row = resolved_ticket_row(status_code="CLOSED")
    service = reopen_service(row, monkeypatch=monkeypatch)
    with pytest.raises(ApplicationError) as excinfo:
        service.reopen(ticket_id=1, actor=REQUESTER, reason="x", now=NOW)
    assert excinfo.value.code == "TICKET_CLOSED"


def test_missing_ticket_raises_404(monkeypatch):
    service = reopen_service(None, monkeypatch=monkeypatch)
    with pytest.raises(ApplicationError) as excinfo:
        service.reopen(ticket_id=1, actor=REQUESTER, reason="x", now=NOW)
    assert excinfo.value.status_code == 404
