"""Regression coverage for B-owned actions merged with C's workflow actions."""

from app.common.request_context import RequestContext
from app.core.enums import AvailableAction, UserRole
from app.domains.tickets.service import TicketService


def _actor(role: UserRole, *, user_id: int = 10) -> RequestContext:
    return RequestContext(user_id=user_id, role=role, vendor_org_id=None)


def test_pending_user_does_not_advertise_ordinary_comment():
    actions = TicketService._actions(
        _actor(UserRole.USER),
        {"status_code": "PENDING_USER", "vendor_request_status": None},
        ["RESUME"],
    )
    assert AvailableAction.RESUME in actions
    assert AvailableAction.COMMENT not in actions


def test_manager_resolved_does_not_reintroduce_assign():
    actions = TicketService._actions(
        _actor(UserRole.SERVICE_DESK_MANAGER),
        {"status_code": "RESOLVED", "vendor_request_status": None},
        [],
    )
    assert AvailableAction.ASSIGN not in actions
    assert AvailableAction.EDIT in actions


def test_closed_ticket_never_has_actions():
    actions = TicketService._actions(
        _actor(UserRole.SERVICE_DESK_MANAGER),
        {"status_code": "CLOSED", "vendor_request_status": None},
        ["ASSIGN"],
    )
    assert actions == []
