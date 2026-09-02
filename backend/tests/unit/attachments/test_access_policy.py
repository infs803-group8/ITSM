import pytest

from app.common.request_context import RequestContext
from app.core.enums import AttachmentVisibility, UserRole
from app.core.errors import ApplicationError
from app.domains.attachments.access_policy import (
    AttachmentAccessPolicy,
    TicketAccessRecord,
)


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


def test_tier1_cannot_create_vendor_shared_attachment():
    actor = RequestContext(user_id=2, role=UserRole.ENGINEER_TIER1)
    with pytest.raises(ApplicationError) as error:
        AttachmentAccessPolicy.ensure_ticket_write(
            ticket(), actor, AttachmentVisibility.VENDOR_SHARED
        )
    assert error.value.code == "DATA_SCOPE_DENIED"
    assert error.value.status_code == 403


def test_tier2_vendor_shared_is_bound_by_backend():
    actor = RequestContext(user_id=2, role=UserRole.ENGINEER_TIER2)
    binding = AttachmentAccessPolicy.ensure_ticket_write(
        ticket(), actor, AttachmentVisibility.VENDOR_SHARED
    )
    assert binding == (90, 8)


def test_vendor_requires_matching_active_request():
    actor = RequestContext(user_id=3, role=UserRole.EXTERNAL_VENDOR, vendor_org_id=7)
    with pytest.raises(ApplicationError) as error:
        AttachmentAccessPolicy.ensure_ticket_write(
            ticket(), actor, AttachmentVisibility.VENDOR_SHARED
        )
    assert error.value.code == "NO_ACTIVE_VENDOR_REQUEST"


def test_hidden_ticket_is_reported_as_not_found():
    actor = RequestContext(user_id=99, role=UserRole.USER)
    with pytest.raises(ApplicationError) as error:
        AttachmentAccessPolicy.ensure_ticket_read(ticket(), actor)
    assert error.value.code == "RESOURCE_NOT_FOUND"
    assert error.value.status_code == 404


def test_closed_ticket_is_readable_but_not_writable():
    actor = RequestContext(user_id=1, role=UserRole.USER)
    AttachmentAccessPolicy.ensure_ticket_read(ticket(status_code="CLOSED"), actor)
    with pytest.raises(ApplicationError) as error:
        AttachmentAccessPolicy.ensure_ticket_write(
            ticket(status_code="CLOSED"),
            actor,
            AttachmentVisibility.USER_VISIBLE,
        )
    assert error.value.code == "TICKET_CLOSED"
