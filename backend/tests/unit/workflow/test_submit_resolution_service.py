"""Unit tests for app.domains.workflow.service.SubmitResolutionService
(C031).

Fake-repository/audit/sla pattern -- same conventions as the other
C025-C030 service tests. Imports SQLAlchemy transitively, so
syntax-checked only (py_compile), not executed.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.common.request_context import RequestContext
from app.contracts.vendor_binding import ActiveVendorBinding
from app.core.errors import ApplicationError
from app.domains.workflow.service import SubmitResolutionService
from app.domains.workflow.state_machine import TicketStatus

NOW = datetime(2026, 9, 1, 0, 0, 0, tzinfo=UTC)
TIER1_ASSIGNEE = RequestContext(user_id=20, role="ENGINEER_TIER1")
TIER2_ASSIGNEE = RequestContext(user_id=30, role="ENGINEER_TIER2")
OTHER_ENGINEER = RequestContext(user_id=21, role="ENGINEER_TIER1")


class WorkflowRepositoryFake:
    def __init__(self, *, ticket_row):
        self.ticket_row = ticket_row
        self.vendor_row = None
        self.applied = None

    def get_ticket_state_row(self, ticket_id):
        return self.ticket_row

    def get_latest_vendor_request(self, ticket_id):
        return self.vendor_row

    def apply_submit_resolution(self, *, ticket_id, pending_user_deadline, resolution_summary):
        self.applied = {
            "ticket_id": ticket_id,
            "pending_user_deadline": pending_user_deadline,
            "resolution_summary": resolution_summary,
        }


class VendorWorkflowRepositoryFake:
    def __init__(self, *, binding=None):
        self.binding = binding
        self.cancelled = None

    def get_active_binding(self, *, ticket_id):
        return self.binding

    def cancel_active_request(self, *, vendor_request_id, cancelled_at, cancelled_by_id, cancellation_reason):
        self.cancelled = {
            "vendor_request_id": vendor_request_id,
            "cancelled_at": cancelled_at,
            "cancelled_by_id": cancelled_by_id,
            "cancellation_reason": cancellation_reason,
        }


class SlaRepositoryFake:
    def __init__(self, *, user_response_hours=120):
        self.user_response_hours = user_response_hours

    def get_user_response_hours(self):
        return self.user_response_hours


class SlaCycleServiceFake:
    def __init__(self, user_response_hours=120):
        self.repository = SlaRepositoryFake(user_response_hours=user_response_hours)


class AuditFake:
    def __init__(self):
        self.events = []
        self._next_id = 9001

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


def pending_vendor_ticket_row(**overrides):
    row = in_progress_ticket_row(
        status_code="PENDING_VENDOR", assignee_id=30, assignee_role_code="ENGINEER_TIER2"
    )
    row.update(overrides)
    return row


def active_binding(**overrides):
    kwargs = {"vendor_request_id": 7001, "vendor_org_id": 5}
    kwargs.update(overrides)
    return ActiveVendorBinding(**kwargs)


def submit_resolution_service(ticket_row, *, vendor_row=None, binding=None, user_response_hours=120):
    service = SubmitResolutionService(None)
    service.repository = WorkflowRepositoryFake(ticket_row=ticket_row)
    service.repository.vendor_row = vendor_row
    service.vendor_repository = VendorWorkflowRepositoryFake(binding=binding)
    service.audit = AuditFake()
    service.sla = SlaCycleServiceFake(user_response_hours=user_response_hours)
    return service


def test_current_assignee_can_resolve_from_in_progress():
    service = submit_resolution_service(in_progress_ticket_row())
    outcome = service.submit_resolution(
        ticket_id=1, actor=TIER1_ASSIGNEE, resolution_summary="Replaced the faulty cable.", now=NOW
    )

    assert outcome.status is TicketStatus.PENDING_USER
    assert outcome.vendor_cancelled_event_id is None
    assert service.repository.applied == {
        "ticket_id": 1,
        "pending_user_deadline": NOW + timedelta(hours=120),
        "resolution_summary": "Replaced the faulty cable.",
    }
    assert service.vendor_repository.cancelled is None
    assert len(service.audit.events) == 1
    event = service.audit.events[0]
    assert event["event_type"].value == "RESOLUTION_SUBMITTED"
    assert event["scope"].value == "USER_VISIBLE"
    assert outcome.event_id == 9001


def test_a_different_engineer_cannot_resolve():
    service = submit_resolution_service(in_progress_ticket_row())
    with pytest.raises(ApplicationError) as excinfo:
        service.submit_resolution(
            ticket_id=1, actor=OTHER_ENGINEER, resolution_summary="x", now=NOW
        )
    assert excinfo.value.code == "DATA_SCOPE_DENIED"
    assert service.repository.applied is None


def test_current_tier2_assignee_can_resolve_from_pending_vendor_and_cancels_the_active_request():
    binding = active_binding()
    service = submit_resolution_service(
        pending_vendor_ticket_row(), vendor_row={"vendor_org_id": 5, "status": "ACTIVE"}, binding=binding
    )
    outcome = service.submit_resolution(
        ticket_id=1, actor=TIER2_ASSIGNEE, resolution_summary="Vendor confirmed a firmware fix; applied directly.", now=NOW
    )

    assert outcome.status is TicketStatus.PENDING_USER
    assert service.vendor_repository.cancelled == {
        "vendor_request_id": 7001,
        "cancelled_at": NOW,
        "cancelled_by_id": 30,
        "cancellation_reason": "Resolved without waiting on vendor response.",
    }
    assert len(service.audit.events) == 2
    cancel_event, resolve_event = service.audit.events
    assert cancel_event["event_type"].value == "VENDOR_CANCELLED"
    assert cancel_event["scope"].value == "VENDOR_SCOPE"
    assert cancel_event["vendor_org_id"] == 5
    assert cancel_event["vendor_request_id"] == 7001
    assert resolve_event["event_type"].value == "RESOLUTION_SUBMITTED"
    assert outcome.vendor_cancelled_event_id == 9001
    assert outcome.event_id == 9002


def test_a_tier1_assignee_cannot_resolve_from_pending_vendor():
    """state_machine._eval_submit_resolution's PENDING_VENDOR branch
    requires actor_role == ENGINEER_TIER2 specifically, unlike the
    IN_PROGRESS branch which accepts any current-assignee role.
    """
    row = pending_vendor_ticket_row(assignee_id=20, assignee_role_code="ENGINEER_TIER1")
    service = submit_resolution_service(
        row, vendor_row={"vendor_org_id": 5, "status": "ACTIVE"}, binding=active_binding()
    )
    with pytest.raises(ApplicationError) as excinfo:
        service.submit_resolution(
            ticket_id=1, actor=TIER1_ASSIGNEE, resolution_summary="x", now=NOW
        )
    assert excinfo.value.code == "DATA_SCOPE_DENIED"
    assert service.vendor_repository.cancelled is None


def test_a_ticket_that_is_neither_in_progress_nor_pending_vendor_is_rejected():
    row = in_progress_ticket_row(status_code="ASSIGNED")
    service = submit_resolution_service(row)
    with pytest.raises(ApplicationError) as excinfo:
        service.submit_resolution(
            ticket_id=1, actor=TIER1_ASSIGNEE, resolution_summary="x", now=NOW
        )
    assert excinfo.value.code == "INVALID_STATUS_TRANSITION"
    assert service.repository.applied is None


def test_a_closed_ticket_is_rejected():
    row = in_progress_ticket_row(status_code="CLOSED")
    service = submit_resolution_service(row)
    with pytest.raises(ApplicationError) as excinfo:
        service.submit_resolution(
            ticket_id=1, actor=TIER1_ASSIGNEE, resolution_summary="x", now=NOW
        )
    assert excinfo.value.code == "TICKET_CLOSED"


def test_missing_ticket_raises_404():
    service = submit_resolution_service(None)
    with pytest.raises(ApplicationError) as excinfo:
        service.submit_resolution(
            ticket_id=1, actor=TIER1_ASSIGNEE, resolution_summary="x", now=NOW
        )
    assert excinfo.value.status_code == 404
