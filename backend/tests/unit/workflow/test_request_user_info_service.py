"""Unit tests for app.domains.workflow.service.RequestUserInfoService (C026).

Fake-repository/audit/sla pattern, plus monkeypatching the module-level
``insert_workflow_comment`` import (comment_gateway is a free function,
not a class attribute, so there is nothing to swap an instance's
attribute for). Imports SQLAlchemy transitively (via action_engine ->
repository, audit.service, sla.service), so syntax-checked only
(py_compile), not executed, in an environment without pip access -- same
convention as every other DB-touching service test in this codebase.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.common.request_context import RequestContext
from app.core.errors import ApplicationError
from app.domains.workflow import service as service_module
from app.domains.workflow.service import RequestUserInfoService
from app.domains.workflow.state_machine import TicketStatus

NOW = datetime(2026, 9, 1, 0, 0, 0, tzinfo=UTC)
USER_TIMER_DEADLINE = NOW + timedelta(hours=120)
ASSIGNEE = RequestContext(user_id=20, role="ENGINEER_TIER1")
OTHER_ENGINEER = RequestContext(user_id=21, role="ENGINEER_TIER1")
REQUESTER = RequestContext(user_id=10, role="USER")


class RepositoryFake:
    def __init__(self, *, ticket_row, vendor_row=None):
        self.ticket_row = ticket_row
        self.vendor_row = vendor_row
        self.applied = None

    def get_ticket_state_row(self, ticket_id):
        return self.ticket_row

    def get_latest_vendor_request(self, ticket_id):
        return self.vendor_row

    def apply_pending_user_transition(
        self, *, ticket_id, status_code, pending_user_reason, pending_user_deadline
    ):
        self.applied = {
            "ticket_id": ticket_id,
            "status_code": status_code,
            "pending_user_reason": pending_user_reason,
            "pending_user_deadline": pending_user_deadline,
        }


class AuditFake:
    def __init__(self):
        self.events = []
        self._next_id = 6001

    def append_event(self, **kwargs):
        self.events.append(kwargs)
        event_id = self._next_id
        self._next_id += 1
        return event_id


class SlaFake:
    def __init__(self):
        self.paused = None

    def pause_current_cycle(self, *, ticket_id, cycle_no, actor_id):
        self.paused = {"ticket_id": ticket_id, "cycle_no": cycle_no, "actor_id": actor_id}

    def compute_user_response_deadline(self, *, now):
        return USER_TIMER_DEADLINE


def in_progress_ticket_row(**overrides):
    row = {
        "ticket_id": 1,
        "status_code": "IN_PROGRESS",
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


def request_user_info_service(ticket_row, *, monkeypatch, inserted_comment_id=7001):
    service = RequestUserInfoService(None)
    service.repository = RepositoryFake(ticket_row=ticket_row)
    service.audit = AuditFake()
    service.sla = SlaFake()
    captured = {}

    def fake_insert_workflow_comment(database, **kwargs):
        captured.update(kwargs)
        return inserted_comment_id

    monkeypatch.setattr(service_module, "insert_workflow_comment", fake_insert_workflow_comment)
    return service, captured


def test_current_assignee_can_request_user_info(monkeypatch):
    service, captured = request_user_info_service(in_progress_ticket_row(), monkeypatch=monkeypatch)
    outcome = service.request_user_info(
        ticket_id=1, actor=ASSIGNEE, message="Please attach a screenshot.", now=NOW
    )

    assert outcome.status is TicketStatus.PENDING_USER
    assert outcome.comment_id == 7001
    assert service.repository.applied["status_code"] == "PENDING_USER"
    assert service.repository.applied["pending_user_reason"].value == "INFORMATION_REQUIRED"
    assert service.repository.applied["pending_user_deadline"] == USER_TIMER_DEADLINE
    assert service.sla.paused == {"ticket_id": 1, "cycle_no": 1, "actor_id": 20}
    assert captured["message"] == "Please attach a screenshot."
    assert captured["workflow_action"] == "REQUEST_USER_INFO"

    # C026.05: a COMMENT_ADDED event referencing the new comment, THEN the
    # USER_INFO_REQUESTED event -- schema.sql's chk_ticket_events_comment_type
    # forbids setting comment_id on any other event type, so these must be
    # two separate rows, not one.
    assert [e["event_type"].value for e in service.audit.events] == [
        "COMMENT_ADDED",
        "USER_INFO_REQUESTED",
    ]
    assert service.audit.events[0]["comment_id"] == 7001
    assert (
        "comment_id" not in service.audit.events[1] or service.audit.events[1]["comment_id"] is None
    )
    # AuditFake hands out 6001 then 6002 -- the outcome's event_id is the
    # USER_INFO_REQUESTED event (the second append_event call), not the
    # COMMENT_ADDED one.
    assert outcome.event_id == 6002


def test_blank_message_is_rejected_before_touching_the_ticket(monkeypatch):
    service, _captured = request_user_info_service(
        in_progress_ticket_row(), monkeypatch=monkeypatch
    )
    with pytest.raises(ApplicationError) as excinfo:
        service.request_user_info(ticket_id=1, actor=ASSIGNEE, message="   ", now=NOW)
    assert excinfo.value.code == "VALIDATION_ERROR"
    assert excinfo.value.status_code == 422
    assert service.repository.applied is None
    assert service.sla.paused is None


def test_a_different_engineer_cannot_request_user_info(monkeypatch):
    service, _captured = request_user_info_service(
        in_progress_ticket_row(), monkeypatch=monkeypatch
    )
    with pytest.raises(ApplicationError) as excinfo:
        service.request_user_info(
            ticket_id=1, actor=OTHER_ENGINEER, message="Need more info.", now=NOW
        )
    assert excinfo.value.code == "DATA_SCOPE_DENIED"
    assert excinfo.value.status_code == 403
    assert service.repository.applied is None


def test_the_requester_cannot_call_this_action(monkeypatch):
    service, _captured = request_user_info_service(
        in_progress_ticket_row(), monkeypatch=monkeypatch
    )
    with pytest.raises(ApplicationError) as excinfo:
        service.request_user_info(ticket_id=1, actor=REQUESTER, message="Need more info.", now=NOW)
    assert excinfo.value.code == "DATA_SCOPE_DENIED"


def test_a_ticket_that_is_not_in_progress_is_rejected(monkeypatch):
    row = in_progress_ticket_row(status_code="ASSIGNED")
    service, _captured = request_user_info_service(row, monkeypatch=monkeypatch)
    with pytest.raises(ApplicationError) as excinfo:
        service.request_user_info(ticket_id=1, actor=ASSIGNEE, message="Need more info.", now=NOW)
    assert excinfo.value.code == "INVALID_STATUS_TRANSITION"
    assert excinfo.value.status_code == 409


def test_a_ticket_already_pending_user_is_rejected_as_a_duplicate_request(monkeypatch):
    row = in_progress_ticket_row(
        status_code="PENDING_USER",
        pending_user_reason="INFORMATION_REQUIRED",
        pending_user_deadline=NOW + timedelta(hours=100),
    )
    service, _captured = request_user_info_service(row, monkeypatch=monkeypatch)
    with pytest.raises(ApplicationError) as excinfo:
        service.request_user_info(ticket_id=1, actor=ASSIGNEE, message="Need more info.", now=NOW)
    assert excinfo.value.code == "INVALID_STATUS_TRANSITION"
    assert service.repository.applied is None


def test_a_closed_ticket_is_rejected(monkeypatch):
    row = in_progress_ticket_row(status_code="CLOSED")
    service, _captured = request_user_info_service(row, monkeypatch=monkeypatch)
    with pytest.raises(ApplicationError) as excinfo:
        service.request_user_info(ticket_id=1, actor=ASSIGNEE, message="Need more info.", now=NOW)
    assert excinfo.value.code == "TICKET_CLOSED"


def test_missing_ticket_raises_404(monkeypatch):
    service, _captured = request_user_info_service(None, monkeypatch=monkeypatch)
    with pytest.raises(ApplicationError) as excinfo:
        service.request_user_info(ticket_id=1, actor=ASSIGNEE, message="Need more info.", now=NOW)
    assert excinfo.value.status_code == 404
