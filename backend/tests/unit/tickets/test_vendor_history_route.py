"""Public Q03 route: ticket scope precedes history-role authorization."""

from datetime import datetime

import pytest

from app.common.request_context import RequestContext
from app.core.errors import ApplicationError
from app.domains.tickets import router

USER = RequestContext(user_id=10, role="USER")
TIER2 = RequestContext(user_id=20, role="ENGINEER_TIER2")


class _RepositoryFake:
    visible_result = True

    def __init__(self, _database):
        pass

    def visible(self, actor, ticket_id):
        return self.visible_result


class _ReaderFake:
    calls = []

    def __init__(self, _database):
        pass

    def list_for_actor(self, *, ticket_id, actor):
        self.calls.append((ticket_id, actor))
        return [
            {
                "vendor_request_id": 300,
                "vendor_org": {
                    "vendor_org_id": 7,
                    "name": "Acme Networks",
                    "is_active": True,
                },
                "status": "RESPONDED",
                "vendor_message": "Please check the switch.",
                "created_at": datetime(2026, 9, 1, 2, 0, 0),
                "responded_at": datetime(2026, 9, 1, 3, 0, 0),
                "response": {
                    "vendor_response_id": 400,
                    "vendor_request_id": 300,
                    "message": "Upgrade the firmware.",
                    "created_at": datetime(2026, 9, 1, 3, 0, 0),
                },
            }
        ]


def test_visible_ticket_returns_typed_history(monkeypatch):
    _RepositoryFake.visible_result = True
    _ReaderFake.calls = []
    monkeypatch.setattr(router, "TicketRepository", _RepositoryFake)
    monkeypatch.setattr(router, "VendorHistoryReader", _ReaderFake)

    response = router.list_vendor_request_history(1, TIER2, object())

    assert _ReaderFake.calls == [(1, TIER2)]
    assert response.data[0].response is not None
    assert response.data[0].response.message == "Upgrade the firmware."
    assert response.data[0].created_at.tzinfo is not None


def test_invisible_ticket_returns_404_before_history_role_check(monkeypatch):
    _RepositoryFake.visible_result = False
    _ReaderFake.calls = []
    monkeypatch.setattr(router, "TicketRepository", _RepositoryFake)
    monkeypatch.setattr(router, "VendorHistoryReader", _ReaderFake)

    with pytest.raises(ApplicationError) as excinfo:
        router.list_vendor_request_history(99, USER, object())

    assert excinfo.value.code == "RESOURCE_NOT_FOUND"
    assert excinfo.value.status_code == 404
    assert _ReaderFake.calls == []
