"""Unit tests for app.domains.workflow.service.ConfirmResolutionService
(C032).

Fake-repository/audit/sla pattern -- same conventions as the other
C025-C031 service tests. Imports SQLAlchemy transitively, so
syntax-checked only (py_compile), not executed.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.common.request_context import RequestContext
from app.core.errors import ApplicationError
from app.domains.workflow.service import ConfirmResolutionService
from app.domains.workflow.state_machine import TicketStatus

NOW = datetime(2026, 9, 1, 0, 0, 0, tzinfo=UTC)
REQUESTER = RequestContext(user_id=10, role="END_USER")
OTHER_USER = RequestContext(user_id=11, role="END_USER")


class WorkflowRepositoryFake:
    def __init__(self, *, ticket_row):
        self.ticket_row = ticket_row
        self.applied = None

    def get_ticket_state_row(self, ticket_id):
        return self.ticket_row

    def get_latest_vendor_request(self, ticket_id):
        return None

    def apply_confirm_resolution(
        self, *, ticket_id, resolution_type, resolved_at, auto_close_at, last_resolved_assignee_id
    ):
        self.applied = {
            "ticket_id": ticket_id,
            "resolution_type": resolution_type,
            "resolved_at": resolved_at,
            "auto_close_at": auto_close_at,
            "last_resolved_assignee_id": last_resolved_assignee_id,
        }


class SlaRepositoryFake:
    def __init__(self, *, resolved_window_hours=168):
        self.resolved_window_hours = resolved_window_hours

    def get_resolved_window_hours(self):
        return self.resolved_window_hours


class SlaCycleServiceFake:
    def __init__(self, *, resolved_window_hours=168):
        self.resolved_window_hours = resolved_window_hours
        self.repository = SlaRepositoryFake(resolved_window_hours=resolved_window_hours)

    def compute_auto_close_deadline(self, *, resolved_at):
        return resolved_at + timedelta(hours=self.resolved_window_hours)


class DeadlineFake:
    """By default the window is still open (never raises); a test that
    needs the expired-window path sets ``self.expired = True``. Same
    fake shape as test_resume_service.py's -- ConfirmResolutionService
    is deadline_service.py's other named caller of
    ``enforce_pending_user_not_expired``.
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


class AuditFake:
    def __init__(self):
        self.events = []
        self._next_id = 10001

    def append_event(self, **kwargs):
        self.events.append(kwargs)
        event_id = self._next_id
        self._next_id += 1
        return event_id


def pending_confirmation_ticket_row(**overrides):
    row = {
        "ticket_id": 1,
        "status_code": "PENDING_USER",
        "requester_id": 10,
        "assignee_id": 20,
        "category_code": "NETWORK",
        "sla_cycle_no": 1,
        "sla_status_code": "ON_TRACK",
        "sla_deadline": NOW + timedelta(hours=30),
        "pending_user_reason": "RESOLUTION_CONFIRMATION",
        "pending_user_deadline": NOW + timedelta(hours=100),
        "resolution_summary": "Replaced the faulty cable.",
        "resolution_type": None,
        "resolved_at": None,
        "auto_close_at": None,
        "closure_type": None,
        "closed_at": None,
        "assignee_role_code": "ENGINEER_TIER1",
    }
    row.update(overrides)
    return row


def confirm_resolution_service(ticket_row, *, resolved_window_hours=168, expired=False):
    service = ConfirmResolutionService(None)
    service.repository = WorkflowRepositoryFake(ticket_row=ticket_row)
    service.audit = AuditFake()
    service.sla = SlaCycleServiceFake(resolved_window_hours=resolved_window_hours)
    service.deadlines = DeadlineFake()
    service.deadlines.expired = expired
    return service


def test_the_requester_can_confirm_a_submitted_resolution():
    service = confirm_resolution_service(pending_confirmation_ticket_row())
    outcome = service.confirm_resolution(ticket_id=1, actor=REQUESTER, now=NOW)

    assert outcome.status is TicketStatus.RESOLVED
    assert service.repository.applied == {
        "ticket_id": 1,
        "resolution_type": "USER_CONFIRMED",
        "resolved_at": NOW,
        "auto_close_at": NOW + timedelta(hours=168),
        "last_resolved_assignee_id": 20,
    }
    assert len(service.audit.events) == 1
    event = service.audit.events[0]
    assert event["event_type"].value == "RESOLUTION_CONFIRMED"
    assert event["scope"].value == "USER_VISIBLE"
    assert outcome.event_id == 10001


def test_an_already_expired_window_reports_auto_resolution_instead_of_confirming():
    """DeadlineService.enforce_pending_user_not_expired's own docstring
    names this action as one of its two callers -- if the 120h window
    already passed, the ticket auto-resolved as AUTO_CONFIRMATION_
    TIMEOUT and this call must report that rather than confirming a
    resolution outcome that no longer matches the database.
    """
    service = confirm_resolution_service(pending_confirmation_ticket_row(), expired=True)
    with pytest.raises(ApplicationError) as excinfo:
        service.confirm_resolution(ticket_id=1, actor=REQUESTER, now=NOW)
    assert excinfo.value.code == "USER_RESPONSE_WINDOW_EXPIRED"
    assert service.repository.applied is None
    assert len(service.deadlines.calls) == 1


def test_a_different_user_cannot_confirm():
    service = confirm_resolution_service(pending_confirmation_ticket_row())
    with pytest.raises(ApplicationError) as excinfo:
        service.confirm_resolution(ticket_id=1, actor=OTHER_USER, now=NOW)
    assert excinfo.value.code == "DATA_SCOPE_DENIED"
    assert service.repository.applied is None


def test_a_pending_user_ticket_that_is_waiting_on_information_not_resolution_is_rejected():
    row = pending_confirmation_ticket_row(pending_user_reason="INFORMATION_REQUIRED")
    service = confirm_resolution_service(row)
    with pytest.raises(ApplicationError) as excinfo:
        service.confirm_resolution(ticket_id=1, actor=REQUESTER, now=NOW)
    assert excinfo.value.code == "INVALID_STATUS_TRANSITION"
    assert service.repository.applied is None


def test_a_ticket_that_is_not_pending_user_at_all_is_rejected():
    row = pending_confirmation_ticket_row(
        status_code="IN_PROGRESS", pending_user_reason=None, pending_user_deadline=None
    )
    service = confirm_resolution_service(row)
    with pytest.raises(ApplicationError) as excinfo:
        service.confirm_resolution(ticket_id=1, actor=REQUESTER, now=NOW)
    assert excinfo.value.code == "INVALID_STATUS_TRANSITION"


def test_a_closed_ticket_is_rejected():
    row = pending_confirmation_ticket_row(
        status_code="CLOSED", pending_user_reason=None, pending_user_deadline=None
    )
    service = confirm_resolution_service(row)
    with pytest.raises(ApplicationError) as excinfo:
        service.confirm_resolution(ticket_id=1, actor=REQUESTER, now=NOW)
    assert excinfo.value.code == "TICKET_CLOSED"


def test_missing_ticket_raises_404():
    service = confirm_resolution_service(None)
    with pytest.raises(ApplicationError) as excinfo:
        service.confirm_resolution(ticket_id=1, actor=REQUESTER, now=NOW)
    assert excinfo.value.status_code == 404
