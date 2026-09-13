"""Unit tests for app.domains.vendor_workflow.service.RequestVendorService
(C029).

Fake-repository/audit pattern -- same conventions as the other C025-C028
service tests. Imports SQLAlchemy transitively (IntegrityError), so
syntax-checked only (py_compile), not executed.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.common.request_context import RequestContext
from app.core.errors import ApplicationError
from app.domains.vendor_workflow.service import RequestVendorService
from app.domains.workflow.state_machine import TicketStatus

NOW = datetime(2026, 9, 1, 0, 0, 0, tzinfo=UTC)
TIER2_ASSIGNEE = RequestContext(user_id=30, role="ENGINEER_TIER2")
OTHER_TIER2 = RequestContext(user_id=31, role="ENGINEER_TIER2")
TIER1_ASSIGNEE = RequestContext(user_id=30, role="ENGINEER_TIER1")


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
    def __init__(self, *, org_row, raise_integrity_error=False, next_id=5001):
        self.org_row = org_row
        self.raise_integrity_error = raise_integrity_error
        self.next_id = next_id
        self.created = None
        self.rolled_back = False

    def get_vendor_organisation(self, vendor_org_id):
        return self.org_row

    def create_active_request(self, *, ticket_id, vendor_org_id, requested_by_id, vendor_message):
        if self.raise_integrity_error:
            raise IntegrityError("INSERT", {}, Exception("duplicate"))
        self.created = {
            "ticket_id": ticket_id,
            "vendor_org_id": vendor_org_id,
            "requested_by_id": requested_by_id,
            "vendor_message": vendor_message,
        }
        return self.next_id


class DatabaseFake:
    def __init__(self):
        self.rolled_back = False

    def rollback(self):
        self.rolled_back = True


class AuditFake:
    def __init__(self):
        self.events = []
        self._next_id = 6001

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


def active_org_row(**overrides):
    row = {"vendor_org_id": 5, "name": "Acme Networking", "is_active": 1}
    row.update(overrides)
    return row


def request_vendor_service(
    ticket_row,
    org_row,
    *,
    vendor_row=None,
    raise_integrity_error=False,
    database=None,
):
    database = database or DatabaseFake()
    service = RequestVendorService(database)
    service.workflow_repository = WorkflowRepositoryFake(ticket_row=ticket_row, vendor_row=vendor_row)
    service.repository = VendorWorkflowRepositoryFake(
        org_row=org_row, raise_integrity_error=raise_integrity_error
    )
    service.audit = AuditFake()
    return service


def test_current_tier2_assignee_can_request_an_active_vendor():
    service = request_vendor_service(in_progress_ticket_row(), active_org_row())
    outcome = service.request_vendor(
        ticket_id=1,
        actor=TIER2_ASSIGNEE,
        vendor_org_id=5,
        vendor_message="Please check the WAN link.",
        now=NOW,
    )

    assert outcome.status is TicketStatus.PENDING_VENDOR
    assert outcome.vendor_request_id == 5001
    assert service.repository.created == {
        "ticket_id": 1,
        "vendor_org_id": 5,
        "requested_by_id": 30,
        "vendor_message": "Please check the WAN link.",
    }
    assert service.workflow_repository.applied_status == {
        "ticket_id": 1,
        "status_code": "PENDING_VENDOR",
    }
    assert len(service.audit.events) == 1
    event = service.audit.events[0]
    assert event["event_type"].value == "VENDOR_REQUESTED"
    assert event["scope"].value == "VENDOR_SCOPE"
    assert event["vendor_org_id"] == 5
    assert event["vendor_request_id"] == 5001
    assert outcome.event_id == 6001


def test_a_different_tier2_engineer_cannot_request_vendor():
    service = request_vendor_service(in_progress_ticket_row(), active_org_row())
    with pytest.raises(ApplicationError) as excinfo:
        service.request_vendor(
            ticket_id=1, actor=OTHER_TIER2, vendor_org_id=5, vendor_message="x", now=NOW
        )
    assert excinfo.value.code == "DATA_SCOPE_DENIED"
    assert service.repository.created is None


def test_a_tier1_engineer_cannot_request_vendor_even_as_assignee():
    """state_machine._eval_request_vendor requires actor_role ==
    ENGINEER_TIER2 specifically, regardless of who the ticket is
    assigned to.
    """
    row = in_progress_ticket_row(assignee_role_code="ENGINEER_TIER1")
    service = request_vendor_service(row, active_org_row())
    with pytest.raises(ApplicationError) as excinfo:
        service.request_vendor(
            ticket_id=1, actor=TIER1_ASSIGNEE, vendor_org_id=5, vendor_message="x", now=NOW
        )
    assert excinfo.value.code == "DATA_SCOPE_DENIED"


def test_a_nonexistent_vendor_organisation_is_rejected():
    service = request_vendor_service(in_progress_ticket_row(), None)
    with pytest.raises(ApplicationError) as excinfo:
        service.request_vendor(
            ticket_id=1, actor=TIER2_ASSIGNEE, vendor_org_id=999, vendor_message="x", now=NOW
        )
    assert excinfo.value.code == "VALIDATION_ERROR"
    assert excinfo.value.status_code == 422
    assert service.repository.created is None


def test_an_inactive_vendor_organisation_is_rejected():
    service = request_vendor_service(in_progress_ticket_row(), active_org_row(is_active=0))
    with pytest.raises(ApplicationError) as excinfo:
        service.request_vendor(
            ticket_id=1, actor=TIER2_ASSIGNEE, vendor_org_id=5, vendor_message="x", now=NOW
        )
    assert excinfo.value.code == "VALIDATION_ERROR"


def test_vendor_org_is_checked_before_the_state_machine_evaluation_runs():
    """A ticket that is not even IN_PROGRESS would also fail
    state_machine's own check -- but an invalid vendor organisation
    should be reported on its own terms rather than masked by
    INVALID_STATUS_TRANSITION, since C029.02 validates it directly
    against the request body's own field.
    """
    row = in_progress_ticket_row(status_code="ASSIGNED")
    service = request_vendor_service(row, None)
    with pytest.raises(ApplicationError) as excinfo:
        service.request_vendor(
            ticket_id=1, actor=TIER2_ASSIGNEE, vendor_org_id=999, vendor_message="x", now=NOW
        )
    assert excinfo.value.code == "VALIDATION_ERROR"


def test_an_already_active_vendor_request_is_denied_by_the_state_machine():
    """The ordinary-case guard: state_machine.has_active_vendor_request is
    already true because ``get_latest_vendor_request`` returns an ACTIVE
    row, so the repository's create_active_request is never reached.
    """
    vendor_row = {"vendor_org_id": 5, "status": "ACTIVE"}
    service = request_vendor_service(
        in_progress_ticket_row(), active_org_row(), vendor_row=vendor_row
    )
    with pytest.raises(ApplicationError) as excinfo:
        service.request_vendor(
            ticket_id=1, actor=TIER2_ASSIGNEE, vendor_org_id=5, vendor_message="x", now=NOW
        )
    assert excinfo.value.code == "ACTIVE_VENDOR_REQUEST_EXISTS"
    assert service.repository.created is None


def test_a_genuine_concurrent_insert_race_is_caught_and_denied():
    """C029.05: the ordinary-case guard above didn't catch it (no ACTIVE
    row was visible to this transaction when it locked the ticket), but
    the database's own unique constraint did -- the resulting
    IntegrityError is rolled back and translated to the same public
    denial as the ordinary case, never leaked raw to the client.
    """
    database = DatabaseFake()
    service = request_vendor_service(
        in_progress_ticket_row(), active_org_row(), raise_integrity_error=True, database=database
    )
    with pytest.raises(ApplicationError) as excinfo:
        service.request_vendor(
            ticket_id=1, actor=TIER2_ASSIGNEE, vendor_org_id=5, vendor_message="x", now=NOW
        )
    assert excinfo.value.code == "ACTIVE_VENDOR_REQUEST_EXISTS"
    assert database.rolled_back is True
    assert service.workflow_repository.applied_status is None


def test_a_ticket_that_is_not_in_progress_is_rejected():
    row = in_progress_ticket_row(status_code="PENDING_USER")
    service = request_vendor_service(row, active_org_row())
    with pytest.raises(ApplicationError) as excinfo:
        service.request_vendor(
            ticket_id=1, actor=TIER2_ASSIGNEE, vendor_org_id=5, vendor_message="x", now=NOW
        )
    assert excinfo.value.code == "INVALID_STATUS_TRANSITION"
    assert service.repository.created is None


def test_a_closed_ticket_is_rejected():
    row = in_progress_ticket_row(status_code="CLOSED")
    service = request_vendor_service(row, active_org_row())
    with pytest.raises(ApplicationError) as excinfo:
        service.request_vendor(
            ticket_id=1, actor=TIER2_ASSIGNEE, vendor_org_id=5, vendor_message="x", now=NOW
        )
    assert excinfo.value.code == "TICKET_CLOSED"


def test_missing_ticket_raises_404():
    service = request_vendor_service(None, active_org_row())
    with pytest.raises(ApplicationError) as excinfo:
        service.request_vendor(
            ticket_id=1, actor=TIER2_ASSIGNEE, vendor_org_id=5, vendor_message="x", now=NOW
        )
    assert excinfo.value.status_code == 404
