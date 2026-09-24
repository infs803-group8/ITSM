"""Unit tests for app.domains.vendor_workflow.service.VendorResponseService
(C030).

Fake-repository/audit pattern -- same conventions as test_request_vendor_
service.py and the other C025-C029 service tests. Imports SQLAlchemy
transitively, so syntax-checked only (py_compile), not executed.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.common.request_context import RequestContext
from app.contracts.vendor_binding import ActiveVendorBinding
from app.core.errors import ApplicationError
from app.domains.vendor_workflow.service import VendorResponseService
from app.domains.workflow.state_machine import TicketStatus

NOW = datetime(2026, 9, 1, 6, 0, 0, tzinfo=UTC)
MATCHING_VENDOR = RequestContext(user_id=40, role="EXTERNAL_VENDOR", vendor_org_id=5)
OTHER_ORG_VENDOR = RequestContext(user_id=41, role="EXTERNAL_VENDOR", vendor_org_id=9)
TIER2_ENGINEER = RequestContext(user_id=30, role="ENGINEER_TIER2")


class WorkflowRepositoryFake:
    def __init__(self, *, ticket_row, vendor_row=None):
        self.ticket_row = ticket_row
        self.vendor_row = vendor_row
        self.applied_status = None

    def get_ticket_state_row(self, ticket_id):
        return self.ticket_row

    def get_latest_vendor_request(self, ticket_id):
        return self.vendor_row

    def apply_status_change(self, *, ticket_id, status_code):
        self.applied_status = {"ticket_id": ticket_id, "status_code": status_code}


class VendorWorkflowRepositoryFake:
    def __init__(self, *, binding, next_response_id=7101):
        self.binding = binding
        self.next_response_id = next_response_id
        self.marked_responded = None
        self.created_response = None

    def get_active_binding(self, *, ticket_id):
        return self.binding

    def mark_request_responded(self, *, vendor_request_id, responded_at):
        self.marked_responded = {
            "vendor_request_id": vendor_request_id,
            "responded_at": responded_at,
        }

    def create_response(self, *, vendor_request_id, responder_id, message):
        self.created_response = {
            "vendor_request_id": vendor_request_id,
            "responder_id": responder_id,
            "message": message,
        }
        return self.next_response_id


class AuditFake:
    def __init__(self):
        self.events = []
        self._next_id = 8001

    def append_event(self, **kwargs):
        self.events.append(kwargs)
        event_id = self._next_id
        self._next_id += 1
        return event_id


def pending_vendor_ticket_row(**overrides):
    row = {
        "ticket_id": 1,
        "status_code": "PENDING_VENDOR",
        "requester_id": 10,
        "assignee_id": 30,
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
        "assignee_role_code": "ENGINEER_TIER2",
    }
    row.update(overrides)
    return row


def active_vendor_row(**overrides):
    row = {"vendor_org_id": 5, "status": "ACTIVE"}
    row.update(overrides)
    return row


def active_binding(**overrides):
    kwargs = {"vendor_request_id": 7001, "vendor_org_id": 5}
    kwargs.update(overrides)
    return ActiveVendorBinding(**kwargs)


def vendor_response_service(ticket_row, *, vendor_row=None, binding=None):
    service = VendorResponseService(None)
    service.workflow_repository = WorkflowRepositoryFake(
        ticket_row=ticket_row, vendor_row=vendor_row
    )
    service.repository = VendorWorkflowRepositoryFake(binding=binding)
    service.audit = AuditFake()
    return service


def test_matching_vendor_can_respond_to_the_active_request():
    service = vendor_response_service(
        pending_vendor_ticket_row(),
        vendor_row=active_vendor_row(),
        binding=active_binding(),
    )
    outcome = service.respond(
        ticket_id=1, actor=MATCHING_VENDOR, message="Apply firmware 4.2.1.", now=NOW
    )

    assert outcome.status is TicketStatus.IN_PROGRESS
    assert outcome.vendor_response_id == 7101
    assert outcome.vendor_request_id == 7001
    assert outcome.message == "Apply firmware 4.2.1."
    assert outcome.created_at == NOW
    assert service.repository.marked_responded == {
        "vendor_request_id": 7001,
        "responded_at": NOW,
    }
    assert service.repository.created_response == {
        "vendor_request_id": 7001,
        "responder_id": 40,
        "message": "Apply firmware 4.2.1.",
    }
    assert service.workflow_repository.applied_status == {
        "ticket_id": 1,
        "status_code": "IN_PROGRESS",
    }
    assert len(service.audit.events) == 1
    event = service.audit.events[0]
    assert event["event_type"].value == "VENDOR_RESPONDED"
    assert event["scope"].value == "VENDOR_SCOPE"
    assert event["vendor_org_id"] == 5
    assert event["vendor_request_id"] == 7001
    assert outcome.event_id == 8001


def test_a_vendor_from_a_different_organisation_is_rejected():
    """state_machine._eval_vendor_response compares actor_vendor_org_id
    against active_vendor_request_org_id -- a different org is rejected
    even though the ticket does have an active request.
    """
    service = vendor_response_service(
        pending_vendor_ticket_row(),
        vendor_row=active_vendor_row(),
        binding=active_binding(),
    )
    with pytest.raises(ApplicationError) as excinfo:
        service.respond(ticket_id=1, actor=OTHER_ORG_VENDOR, message="x", now=NOW)
    assert excinfo.value.code == "DATA_SCOPE_DENIED"
    assert service.repository.marked_responded is None
    assert service.repository.created_response is None


def test_a_non_vendor_actor_cannot_respond():
    service = vendor_response_service(
        pending_vendor_ticket_row(),
        vendor_row=active_vendor_row(),
        binding=active_binding(),
    )
    with pytest.raises(ApplicationError) as excinfo:
        service.respond(ticket_id=1, actor=TIER2_ENGINEER, message="x", now=NOW)
    assert excinfo.value.code == "DATA_SCOPE_DENIED"


def test_a_ticket_with_no_active_vendor_request_is_rejected():
    """A PENDING_VENDOR ticket whose vendor request is not (or no longer)
    ACTIVE -- state_machine's own has_active_vendor_request check catches
    this distinctly from the wrong-status case below.
    """
    row = pending_vendor_ticket_row()
    service = vendor_response_service(row, vendor_row=None, binding=None)
    with pytest.raises(ApplicationError) as excinfo:
        service.respond(ticket_id=1, actor=MATCHING_VENDOR, message="x", now=NOW)
    assert excinfo.value.code == "NO_ACTIVE_VENDOR_REQUEST"
    assert service.repository.marked_responded is None


def test_a_ticket_that_is_not_pending_vendor_is_rejected():
    row = pending_vendor_ticket_row(status_code="IN_PROGRESS")
    service = vendor_response_service(row, vendor_row=active_vendor_row(), binding=active_binding())
    with pytest.raises(ApplicationError) as excinfo:
        service.respond(ticket_id=1, actor=MATCHING_VENDOR, message="x", now=NOW)
    assert excinfo.value.code == "INVALID_STATUS_TRANSITION"
    assert service.repository.marked_responded is None


def test_a_closed_ticket_is_rejected():
    row = pending_vendor_ticket_row(status_code="CLOSED")
    service = vendor_response_service(row, vendor_row=active_vendor_row(), binding=active_binding())
    with pytest.raises(ApplicationError) as excinfo:
        service.respond(ticket_id=1, actor=MATCHING_VENDOR, message="x", now=NOW)
    assert excinfo.value.code == "TICKET_CLOSED"


def test_missing_ticket_raises_404():
    service = vendor_response_service(
        None, vendor_row=active_vendor_row(), binding=active_binding()
    )
    with pytest.raises(ApplicationError) as excinfo:
        service.respond(ticket_id=1, actor=MATCHING_VENDOR, message="x", now=NOW)
    assert excinfo.value.status_code == 404
