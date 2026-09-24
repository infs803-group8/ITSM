import pytest

from app.common.request_context import RequestContext
from app.core.enums import EventScope, UserRole
from app.core.errors import ApplicationError
from app.domains.audit.access_policy import AuditAccessPolicy, TicketAccessRecord


def ticket(**overrides) -> TicketAccessRecord:
    values = {
        "ticket_id": 10,
        "requester_id": 1,
        "assignee_id": 2,
        "status_code": "IN_PROGRESS",
        "active_vendor_request_id": 90,
        "active_vendor_org_id": 8,
        "actor_has_vendor_history": True,
    }
    values.update(overrides)
    return TicketAccessRecord(**values)


def test_hidden_ticket_is_reported_as_not_found():
    actor = RequestContext(user_id=99, role=UserRole.USER)
    with pytest.raises(ApplicationError) as error:
        AuditAccessPolicy.ensure_ticket_read(ticket(), actor)
    assert error.value.code == "RESOURCE_NOT_FOUND"
    assert error.value.status_code == 404


def test_missing_ticket_record_is_reported_as_not_found():
    actor = RequestContext(user_id=1, role=UserRole.USER)
    with pytest.raises(ApplicationError) as error:
        AuditAccessPolicy.ensure_ticket_read(None, actor)
    assert error.value.code == "RESOURCE_NOT_FOUND"


def test_requester_can_read_own_ticket_events():
    actor = RequestContext(user_id=1, role=UserRole.USER)
    AuditAccessPolicy.ensure_ticket_read(ticket(), actor)


def test_vendor_without_history_is_reported_as_not_found():
    actor = RequestContext(user_id=3, role=UserRole.EXTERNAL_VENDOR, vendor_org_id=7)
    with pytest.raises(ApplicationError) as error:
        AuditAccessPolicy.ensure_ticket_read(ticket(actor_has_vendor_history=False), actor)
    assert error.value.code == "RESOURCE_NOT_FOUND"


def test_user_can_only_read_user_visible_scope():
    actor = RequestContext(user_id=1, role=UserRole.USER)
    assert AuditAccessPolicy.readable_scopes(actor) == {EventScope.USER_VISIBLE}


def test_tier1_cannot_read_vendor_scope():
    actor = RequestContext(user_id=2, role=UserRole.ENGINEER_TIER1)
    assert AuditAccessPolicy.readable_scopes(actor) == {
        EventScope.USER_VISIBLE,
        EventScope.INTERNAL_ONLY,
    }


def test_manager_reads_every_scope():
    actor = RequestContext(user_id=4, role=UserRole.SERVICE_DESK_MANAGER)
    assert AuditAccessPolicy.readable_scopes(actor) == set(EventScope)


def test_requesting_a_scope_outside_the_allowed_set_is_denied():
    actor = RequestContext(user_id=1, role=UserRole.USER)
    with pytest.raises(ApplicationError) as error:
        AuditAccessPolicy.resolve_scope_filter(actor, EventScope.INTERNAL_ONLY)
    assert error.value.code == "DATA_SCOPE_DENIED"
    assert error.value.status_code == 403


def test_requesting_an_allowed_scope_narrows_the_filter():
    actor = RequestContext(user_id=2, role=UserRole.ENGINEER_TIER2)
    assert AuditAccessPolicy.resolve_scope_filter(actor, EventScope.USER_VISIBLE) == {
        EventScope.USER_VISIBLE
    }


def test_no_requested_scope_returns_every_allowed_scope():
    actor = RequestContext(user_id=2, role=UserRole.ENGINEER_TIER1)
    assert AuditAccessPolicy.resolve_scope_filter(actor, None) == {
        EventScope.USER_VISIBLE,
        EventScope.INTERNAL_ONLY,
    }
