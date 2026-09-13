"""Unit tests for app.domains.workflow.service.ResumeTicketService (C027).

Fake-repository/audit/sla/deadlines pattern, plus monkeypatching the
module-level ``insert_workflow_comment`` import -- same conventions as
``test_request_user_info_service.py``. ``DeadlineService`` is faked as a
whole object (not just its own repository/audit) because
``ResumeTicketService.__init__`` constructs its own
``DeadlineService(database)`` internally, which in turn builds its own
(unfaked) ``WorkflowRepository``/``AuditService`` -- there is nothing on
the real ``DeadlineService`` a test could safely swap piecemeal, so this
fake speaks only the one method ``ResumeTicketService`` actually calls,
``enforce_pending_user_not_expired``. Imports SQLAlchemy transitively, so
syntax-checked only (py_compile), not executed.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.common.request_context import RequestContext
from app.core.errors import ApplicationError
from app.domains.workflow import service as service_module
from app.domains.workflow.service import ResumeTicketService
from app.domains.workflow.state_machine import TicketStatus

NOW = datetime(2026, 9, 1, 0, 0, 0, tzinfo=UTC)
REQUESTER = RequestContext(user_id=10, role="USER")
OTHER_USER = RequestContext(user_id=11, role="USER")
ASSIGNEE = RequestContext(user_id=20, role="ENGINEER_TIER1")


class RepositoryFake:
    def __init__(self, *, ticket_row, vendor_row=None):
        self.ticket_row = ticket_row
        self.vendor_row = vendor_row
        self.resumed_ticket_id = None

    def get_ticket_state_row(self, ticket_id):
        return self.ticket_row

    def get_latest_vendor_request(self, ticket_id):
        return self.vendor_row

    def apply_resume(self, *, ticket_id):
        self.resumed_ticket_id = ticket_id


class AuditFake:
    def __init__(self):
        self.events = []
        self._next_id = 8001

    def append_event(self, **kwargs):
        self.events.append(kwargs)
        event_id = self._next_id
        self._next_id += 1
        return event_id


class SlaRepositoryFake:
    def get_resolved_window_hours(self):
        return 168


class SlaFake:
    def __init__(self):
        self.repository = SlaRepositoryFake()
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
    needs the expired-window path sets ``self.expired = True``.
    """

    def __init__(self):
        self.expired = False
        self.calls = []

    def enforce_pending_user_not_expired(self, snapshot, *, now, resolved_window_hours):
        self.calls.append(
            {"snapshot": snapshot, "now": now, "resolved_window_hours": resolved_window_hours}
        )
        if self.expired:
            raise ApplicationError(
                "USER_RESPONSE_WINDOW_EXPIRED",
                "The user response window has expired; the ticket was automatically resolved.",
                409,
            )


def pending_user_ticket_row(**overrides):
    row = {
        "ticket_id": 1,
        "status_code": "PENDING_USER",
        "requester_id": 10,
        "assignee_id": 20,
        "category_code": "NETWORK",
        "sla_cycle_no": 2,
        "sla_status_code": "PAUSED",
        "sla_deadline": NOW + timedelta(hours=10),
        "pending_user_reason": "INFORMATION_REQUIRED",
        "pending_user_deadline": NOW + timedelta(hours=50),
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


def resume_service(ticket_row, *, monkeypatch, inserted_comment_id=9001):
    service = ResumeTicketService(None)
    service.repository = RepositoryFake(ticket_row=ticket_row)
    service.audit = AuditFake()
    service.sla = SlaFake()
    service.deadlines = DeadlineFake()
    captured = {}

    def fake_insert_workflow_comment(database, **kwargs):
        captured.update(kwargs)
        return inserted_comment_id

    monkeypatch.setattr(service_module, "insert_workflow_comment", fake_insert_workflow_comment)
    return service, captured


def test_requester_can_resume_from_information_required(monkeypatch):
    service, captured = resume_service(pending_user_ticket_row(), monkeypatch=monkeypatch)
    outcome = service.resume(ticket_id=1, actor=REQUESTER, message="Here is the log file.", now=NOW)

    assert outcome.status is TicketStatus.IN_PROGRESS
    assert outcome.comment_id == 9001
    assert service.repository.resumed_ticket_id == 1
    assert captured["message"] == "Here is the log file."
    assert captured["workflow_action"] == "USER_RESUME"

    # C027.05: a new cycle plus exactly two of this action's own events
    # (COMMENT_ADDED then USER_RESUMED) -- SLA_CYCLE_STARTED is written
    # by SlaFake.start_new_cycle, not through the AuditFake here, so it
    # never appears in service.audit.events.
    assert [e["event_type"].value for e in service.audit.events] == [
        "COMMENT_ADDED",
        "USER_RESUMED",
    ]
    assert service.audit.events[0]["comment_id"] == 9001
    assert outcome.event_id == 8002

    assert service.sla.started_cycle == {
        "ticket_id": 1,
        "previous_cycle_no": 2,
        "actor_id": 10,
        "now": NOW,
        "config": "CONFIG-SENTINEL",
    }

    # C027.02: Deadline Enforcement ran, with the resolved_window_hours
    # SlaRepositoryFake supplies.
    assert len(service.deadlines.calls) == 1
    assert service.deadlines.calls[0]["resolved_window_hours"] == 168
    assert service.deadlines.calls[0]["snapshot"].pending_user_reason.value == "INFORMATION_REQUIRED"


def test_requester_can_resume_issue_persists_from_resolution_confirmation(monkeypatch):
    row = pending_user_ticket_row(
        pending_user_reason="RESOLUTION_CONFIRMATION",
        resolution_summary="Restarted the switch; awaiting confirmation.",
    )
    service, _captured = resume_service(row, monkeypatch=monkeypatch)
    outcome = service.resume(ticket_id=1, actor=REQUESTER, message="Still broken.", now=NOW)

    assert outcome.status is TicketStatus.IN_PROGRESS
    # C027.04: apply_resume unconditionally clears resolution_summary --
    # RepositoryFake doesn't retain field-level state, but the fact that
    # apply_resume was actually invoked (rather than some other, more
    # cautious method) is what this test is really pinning down.
    assert service.repository.resumed_ticket_id == 1


def test_a_non_requester_user_cannot_resume(monkeypatch):
    service, _captured = resume_service(pending_user_ticket_row(), monkeypatch=monkeypatch)
    with pytest.raises(ApplicationError) as excinfo:
        service.resume(ticket_id=1, actor=OTHER_USER, message="Here you go.", now=NOW)
    assert excinfo.value.code == "DATA_SCOPE_DENIED"
    assert service.repository.resumed_ticket_id is None


def test_the_assignee_cannot_resume_on_the_requesters_behalf(monkeypatch):
    service, _captured = resume_service(pending_user_ticket_row(), monkeypatch=monkeypatch)
    with pytest.raises(ApplicationError) as excinfo:
        service.resume(ticket_id=1, actor=ASSIGNEE, message="Here you go.", now=NOW)
    assert excinfo.value.code == "DATA_SCOPE_DENIED"


def test_blank_message_is_rejected_before_touching_the_ticket(monkeypatch):
    service, _captured = resume_service(pending_user_ticket_row(), monkeypatch=monkeypatch)
    with pytest.raises(ApplicationError) as excinfo:
        service.resume(ticket_id=1, actor=REQUESTER, message="\n\t ", now=NOW)
    assert excinfo.value.code == "VALIDATION_ERROR"
    assert excinfo.value.status_code == 422
    assert service.repository.resumed_ticket_id is None
    assert service.deadlines.calls == []


def test_an_already_expired_window_is_reported_as_expired_not_resumed(monkeypatch):
    """C027.06: the deadline has already passed -- DeadlineService commits
    its own auto-resolve outcome and raises; Resume must never proceed
    past that point.
    """
    service, _captured = resume_service(pending_user_ticket_row(), monkeypatch=monkeypatch)
    service.deadlines.expired = True
    with pytest.raises(ApplicationError) as excinfo:
        service.resume(ticket_id=1, actor=REQUESTER, message="Here you go.", now=NOW)
    assert excinfo.value.code == "USER_RESPONSE_WINDOW_EXPIRED"
    assert excinfo.value.status_code == 409
    assert service.repository.resumed_ticket_id is None
    assert service.sla.started_cycle is None


def test_a_ticket_that_is_not_pending_user_is_rejected_without_checking_the_deadline(monkeypatch):
    row = pending_user_ticket_row(
        status_code="IN_PROGRESS", pending_user_reason=None, pending_user_deadline=None
    )
    service, _captured = resume_service(row, monkeypatch=monkeypatch)
    with pytest.raises(ApplicationError) as excinfo:
        service.resume(ticket_id=1, actor=REQUESTER, message="Here you go.", now=NOW)
    assert excinfo.value.code == "INVALID_STATUS_TRANSITION"
    # Deadline Enforcement is only meaningful for a PENDING_USER ticket --
    # it must not even be consulted for a ticket in some other status.
    assert service.deadlines.calls == []


def test_a_closed_ticket_is_rejected(monkeypatch):
    row = pending_user_ticket_row(
        status_code="CLOSED", pending_user_reason=None, pending_user_deadline=None
    )
    service, _captured = resume_service(row, monkeypatch=monkeypatch)
    with pytest.raises(ApplicationError) as excinfo:
        service.resume(ticket_id=1, actor=REQUESTER, message="Here you go.", now=NOW)
    assert excinfo.value.code == "TICKET_CLOSED"


def test_missing_ticket_raises_404(monkeypatch):
    service, _captured = resume_service(None, monkeypatch=monkeypatch)
    with pytest.raises(ApplicationError) as excinfo:
        service.resume(ticket_id=1, actor=REQUESTER, message="Here you go.", now=NOW)
    assert excinfo.value.status_code == 404
