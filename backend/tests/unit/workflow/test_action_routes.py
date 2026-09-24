"""Route-level success tests for the shared write-path response
(``workflow.router.build_ticket_action_response``), used by API-22..31.

Service-only tests could not catch the ITSM check-report P1 where the
response helper read ``ticket.vendor_request`` from the plain dict
``assemble_ticket_detail`` returns: the action had already been committed,
yet the client received HTTP 500. These tests drive the real FastAPI
routes, the real ``assemble_ticket_detail`` and the real response models;
only the action service, the actor, the database session and the two DB
reads are faked. Core ticket timestamps are naive, exactly as raw SQL
returns MySQL DATETIME values.
"""

from dataclasses import dataclass
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_actor, get_db
from app.common.request_context import RequestContext
from app.domains.vendor_workflow import router as vendor_router
from app.domains.workflow import router as workflow_router
from app.domains.workflow import ticket_detail
from app.domains.workflow.read_model import WorkflowReadModel
from app.main import app

ENGINEER = RequestContext(user_id=20, role="ENGINEER_TIER2")
VENDOR = RequestContext(user_id=40, role="EXTERNAL_VENDOR", vendor_org_id=7)

VENDOR_REQUEST = {
    "vendor_request_id": 300,
    "vendor_org": {"vendor_org_id": 7, "name": "Acme Networks", "is_active": True},
    "status": "ACTIVE",
    "vendor_message": "Please check the switch firmware.",
    "created_at": "2026-09-01T02:00:00Z",
    "responded_at": None,
}


class SessionFake:
    def __init__(self):
        self.committed = False

    def commit(self):
        self.committed = True


@dataclass(frozen=True)
class OutcomeFake:
    event_id: int
    vendor_request_id: int = 300
    vendor_response_id: int = 400
    message: str = "Firmware updated."
    created_at: datetime = datetime(2026, 9, 1, 3, 0, 0)


def ticket_core_row():
    return {
        "ticket_id": 1,
        "title": "VPN drops every hour",
        "description": "Disconnects on the hour.",
        "category_code": "NETWORK",
        "priority_code": "HIGH",
        # Naive, as MySQL DATETIME comes back through raw SQL.
        "created_at": datetime(2026, 9, 1, 0, 0, 0),
        "updated_at": datetime(2026, 9, 1, 1, 0, 0),
    }


def role_view(*, status="IN_PROGRESS", vendor_request=None, actions=("RESOLVE",)):
    return {
        "status": status,
        "display_status": status,
        "requester": {"user_id": 10, "display_name": "Requester"},
        "assignee": None,
        "sla": {
            "cycle_no": 1,
            "status": "ON_TRACK",
            "started_at": "2026-09-01T00:00:00Z",
            "deadline": "2026-09-03T00:00:00Z",
        },
        "pending_user": None,
        "resolution": None,
        "closure": None,
        "vendor_request": vendor_request,
        "available_actions": list(actions),
    }


@pytest.fixture
def api(monkeypatch):
    session = SessionFake()
    state = {"actor": ENGINEER, "view": role_view()}

    monkeypatch.setattr(ticket_detail, "_get_ticket_core", lambda _db, _id: ticket_core_row())
    monkeypatch.setattr(
        WorkflowReadModel, "get_role_view", lambda self, *, ticket_id, actor: state["view"]
    )
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_current_actor] = lambda: state["actor"]
    try:
        yield TestClient(app, raise_server_exceptions=False), session, state, monkeypatch
    finally:
        app.dependency_overrides.clear()


def assert_utc(value: str):
    assert value.endswith("Z") or value.endswith("+00:00"), value


def test_start_route_returns_200_with_full_ticket_after_commit(api):
    client, session, _state, monkeypatch = api

    class StartFake:
        def __init__(self, _database):
            pass

        def start(self, *, ticket_id, actor):
            return OutcomeFake(event_id=5001)

    monkeypatch.setattr(workflow_router, "StartTicketService", StartFake)

    response = client.post("/api/v1/tickets/1/start")

    assert response.status_code == 200, response.text
    assert session.committed is True
    data = response.json()["data"]
    assert data["action"] == "START"
    assert data["event_id"] == 5001
    assert data["vendor_request"] is None
    assert data["ticket"]["ticket_id"] == 1
    assert data["ticket"]["status"] == "IN_PROGRESS"
    assert_utc(data["ticket"]["created_at"])
    assert_utc(data["ticket"]["updated_at"])


def test_request_vendor_route_mirrors_ticket_vendor_request_at_top_level(api):
    client, session, state, monkeypatch = api
    state["view"] = role_view(status="PENDING_VENDOR", vendor_request=VENDOR_REQUEST, actions=())

    class RequestVendorFake:
        def __init__(self, _database):
            pass

        def request_vendor(self, *, ticket_id, actor, vendor_org_id, vendor_message):
            return OutcomeFake(event_id=5002)

    monkeypatch.setattr(vendor_router, "RequestVendorService", RequestVendorFake)

    response = client.post(
        "/api/v1/tickets/1/vendor-requests",
        json={"vendor_org_id": 7, "vendor_message": "Please check the switch firmware."},
    )

    assert response.status_code == 201, response.text
    assert session.committed is True
    data = response.json()["data"]
    assert data["action"] == "REQUEST_VENDOR"
    assert data["vendor_request"]["vendor_request_id"] == 300
    assert data["vendor_request"] == data["ticket"]["vendor_request"]


def test_vendor_response_route_returns_200_for_vendor(api):
    client, session, state, monkeypatch = api
    state["actor"] = VENDOR
    state["view"] = role_view(
        status="IN_PROGRESS",
        vendor_request={
            **VENDOR_REQUEST,
            "status": "RESPONDED",
            "responded_at": "2026-09-01T03:00:00Z",
        },
        actions=(),
    )

    class VendorResponseFake:
        def __init__(self, _database):
            pass

        def respond(self, *, ticket_id, actor, message):
            return OutcomeFake(event_id=5003)

    monkeypatch.setattr(vendor_router, "VendorResponseService", VendorResponseFake)

    response = client.post(
        "/api/v1/tickets/1/vendor-response", json={"message": "Firmware updated."}
    )

    assert response.status_code == 200, response.text
    assert session.committed is True
    data = response.json()["data"]
    assert data["action"] == "VENDOR_RESPONSE"
    assert data["vendor_response"]["vendor_response_id"] == 400
    assert data["vendor_request"]["status"] == "RESPONDED"
    assert data["ticket"]["description"] is None
