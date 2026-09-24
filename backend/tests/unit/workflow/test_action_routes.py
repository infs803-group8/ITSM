"""Route-level tests for the shared write-path response
(``workflow.router.build_ticket_action_response``), used by API-21..31.

Every action response is assembled by Member B's shared
``tickets.detail_assembler`` -- the same assembler GET detail (API-17)
uses. These tests drive the real FastAPI routes, the real assembler, the
real ``merge_available_actions`` and the real response models; only the
action services, the actor, the database session and the two DB reads
(``TicketRepository.detail`` and ``WorkflowReadModel.get_role_view``) are
faked. Core ticket timestamps are naive, exactly as MySQL DATETIME comes
back through raw SQL.

The consistency tests are the regression guard for the ITSM check report
P2 items: an action response must never disagree with a subsequent GET on
``available_actions`` or on timestamps.
"""

from dataclasses import dataclass
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_actor, get_db
from app.common.request_context import RequestContext
from app.domains.assignment import router as assignment_router
from app.domains.tickets import detail_assembler
from app.domains.vendor_workflow import router as vendor_router
from app.domains.workflow import router as workflow_router
from app.main import app

USER = RequestContext(user_id=10, role="USER")
TIER1 = RequestContext(user_id=19, role="ENGINEER_TIER1")
TIER2 = RequestContext(user_id=20, role="ENGINEER_TIER2")
MANAGER = RequestContext(user_id=1, role="SERVICE_DESK_MANAGER")
VENDOR = RequestContext(user_id=40, role="EXTERNAL_VENDOR", vendor_org_id=7)

VENDOR_REQUEST = {
    "vendor_request_id": 300,
    "vendor_org": {"vendor_org_id": 7, "name": "Acme Networks", "is_active": True},
    "status": "ACTIVE",
    "vendor_message": "Please check the switch firmware.",
    "created_at": "2026-09-01T02:00:00+00:00",
    "responded_at": None,
}
RESPONDED_VENDOR_REQUEST = {
    **VENDOR_REQUEST,
    "status": "RESPONDED",
    "responded_at": "2026-09-01T03:00:00+00:00",
}


class SessionFake:
    def __init__(self):
        self.committed = False

    def commit(self):
        self.committed = True

    def rollback(self):
        pass


@dataclass(frozen=True)
class OutcomeFake:
    event_id: int = 5001
    comment_id: int | None = None
    vendor_request_id: int = 300
    vendor_response_id: int = 400
    message: str = "Firmware updated."
    created_at: datetime = datetime(2026, 9, 1, 3, 0, 0)


class ServiceFake:
    """Stands in for any action service: every method returns an outcome."""

    def __init__(self, _database):
        pass

    def __getattr__(self, _name):
        return lambda **_kwargs: OutcomeFake()


def ticket_row(*, status="IN_PROGRESS", vendor_request_status=None, assignee_id=20):
    return {
        "ticket_id": 1,
        "requester_id": 10,
        "assignee_id": assignee_id,
        "title": "VPN drops every hour",
        "description": "Disconnects on the hour.",
        "category_code": "NETWORK",
        "priority_code": "HIGH",
        "status_code": status,
        "vendor_request_status": vendor_request_status,
        # Naive, as MySQL DATETIME comes back through raw SQL.
        "created_at": datetime(2026, 9, 1, 0, 0, 0),
        "updated_at": datetime(2026, 9, 1, 1, 0, 0),
    }


def role_view(*, status="IN_PROGRESS", vendor_request=None, actions=()):
    return {
        "status": status,
        "display_status": status,
        "requester": {"user_id": 10, "display_name": "Requester"},
        "assignee": None,
        "sla": {
            "cycle_no": 1,
            "status": "ON_TRACK",
            "started_at": "2026-09-01T00:00:00+00:00",
            "deadline": "2026-09-03T00:00:00+00:00",
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
    state = {
        "actor": TIER2,
        "row": ticket_row(),
        "view": role_view(actions=("RESOLVE",)),
        "authorized_calls": [],
    }

    def in_scope(actor):
        # Mirrors TicketRepository.scope_sql.
        row = state["row"]
        if actor.role == "SERVICE_DESK_MANAGER":
            return True
        if actor.role == "USER":
            return row["requester_id"] == actor.user_id
        if actor.role in {"ENGINEER_TIER1", "ENGINEER_TIER2"}:
            return row["assignee_id"] == actor.user_id
        return actor.role == "EXTERNAL_VENDOR"

    class TicketRepositoryFake:
        def __init__(self, _database):
            pass

        def detail(self, actor, _ticket_id, *, visibility_already_authorized=False):
            state["authorized_calls"].append(visibility_already_authorized)
            if not visibility_already_authorized and not in_scope(actor):
                return None
            return state["row"]

        def visible(self, actor, _ticket_id):
            return in_scope(actor)

    class WorkflowReadModelFake:
        def __init__(self, _database):
            pass

        def get_role_view(self, *, ticket_id, actor):
            return state["view"]

    monkeypatch.setattr(detail_assembler, "TicketRepository", TicketRepositoryFake)
    monkeypatch.setattr(detail_assembler, "WorkflowReadModel", WorkflowReadModelFake)
    for module, name in ROUTES_SERVICES:
        monkeypatch.setattr(module, name, ServiceFake)
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_current_actor] = lambda: state["actor"]
    try:
        yield TestClient(app, raise_server_exceptions=False), session, state
    finally:
        app.dependency_overrides.clear()


ROUTES_SERVICES = [
    (assignment_router, "AssignTicketService"),
    (workflow_router, "StartTicketService"),
    (workflow_router, "RequestUserInfoService"),
    (workflow_router, "ResumeTicketService"),
    (workflow_router, "EscalateTicketService"),
    (workflow_router, "SubmitResolutionService"),
    (workflow_router, "ConfirmResolutionService"),
    (workflow_router, "ReopenTicketService"),
    (workflow_router, "ManualCloseService"),
    (vendor_router, "RequestVendorService"),
    (vendor_router, "VendorResponseService"),
]

# (API, path suffix, body, expected status, action label)
ACTIONS = [
    ("API-21", "assign", {"assignee_id": 20}, 200, "ASSIGN"),
    ("API-22", "start", None, 200, "START"),
    ("API-23", "request-user-info", {"message": "Which VPN client?"}, 200, "REQUEST_USER_INFO"),
    ("API-24", "resume", {"message": "Version 5."}, 200, "RESUME"),
    ("API-25", "escalate", {"tier2_assignee_id": 20}, 200, "ESCALATE"),
    (
        "API-26",
        "vendor-requests",
        {"vendor_org_id": 7, "vendor_message": "Check it."},
        201,
        "REQUEST_VENDOR",
    ),
    ("API-27", "vendor-response", {"message": "Firmware updated."}, 200, "VENDOR_RESPONSE"),
    ("API-28", "resolve", {"resolution_summary": "Replaced the cable."}, 200, "RESOLVE"),
    ("API-29", "confirm-resolution", None, 200, "CONFIRM_RESOLUTION"),
    ("API-30", "reopen", {"reason": "It happened again."}, 200, "REOPEN"),
    ("API-31", "close", {"acknowledge": True}, 200, "CLOSE"),
]


def post_action(client, suffix, body):
    if body is None:
        return client.post(f"/api/v1/tickets/1/{suffix}")
    return client.post(f"/api/v1/tickets/1/{suffix}", json=body)


def assert_utc(value: str):
    assert value.endswith("Z") or value.endswith("+00:00"), value


@pytest.mark.parametrize(("api_id", "suffix", "body", "expected", "action"), ACTIONS)
def test_every_action_route_returns_the_same_ticket_as_get_detail(
    api, api_id, suffix, body, expected, action
):
    client, session, _state = api

    response = post_action(client, suffix, body)

    assert response.status_code == expected, f"{api_id}: {response.text}"
    assert session.committed is True
    data = response.json()["data"]
    assert data["action"] == action
    assert data["event_id"] == 5001
    assert_utc(data["ticket"]["created_at"])
    assert_utc(data["ticket"]["updated_at"])

    detail = client.get("/api/v1/tickets/1")
    assert detail.status_code == 200, detail.text
    assert data["ticket"] == detail.json()["data"]


def test_report_case_responded_vendor_gets_no_comment_upload_or_response(api):
    """ITSM check report P2 #3: once the vendor has replied (no ACTIVE
    request) the old workflow-local assembler still offered COMMENT and
    UPLOAD_ATTACHMENT in the action response while GET did not."""
    client, _session, state = api
    state["actor"] = VENDOR
    state["row"] = ticket_row(status="IN_PROGRESS", vendor_request_status="RESPONDED")
    state["view"] = role_view(vendor_request=RESPONDED_VENDOR_REQUEST)

    response = client.post("/api/v1/tickets/1/vendor-response", json={"message": "Done."})

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["ticket"]["available_actions"] == []
    assert data["ticket"]["description"] is None
    assert data["vendor_request"]["status"] == "RESPONDED"
    assert data["vendor_response"]["vendor_response_id"] == 400
    assert_utc(data["vendor_response"]["created_at"])
    assert data["ticket"] == client.get("/api/v1/tickets/1").json()["data"]


def test_tier2_request_vendor_mirrors_ticket_vendor_request_at_top_level(api):
    client, _session, state = api
    state["row"] = ticket_row(status="PENDING_VENDOR", vendor_request_status="ACTIVE")
    state["view"] = role_view(status="PENDING_VENDOR", vendor_request=VENDOR_REQUEST)

    response = client.post(
        "/api/v1/tickets/1/vendor-requests",
        json={"vendor_org_id": 7, "vendor_message": "Please check the switch firmware."},
    )

    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["vendor_request"]["vendor_request_id"] == 300
    assert data["vendor_request"] == data["ticket"]["vendor_request"]


def test_tier1_never_gets_vendor_request_in_ticket_or_top_level(api):
    """B's Tier 1 vendor payload isolation (#47) must hold for action
    responses too, including the top-level mirror."""
    client, _session, state = api
    state["actor"] = TIER1
    state["row"] = ticket_row(status="ASSIGNED", vendor_request_status="RESPONDED", assignee_id=19)
    state["view"] = role_view(
        status="ASSIGNED", vendor_request=RESPONDED_VENDOR_REQUEST, actions=("START",)
    )

    response = client.post("/api/v1/tickets/1/start")

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["ticket"]["vendor_request"] is None
    assert data["vendor_request"] is None


def test_closed_ticket_action_response_has_no_available_actions(api):
    client, _session, state = api
    state["actor"] = MANAGER
    state["row"] = ticket_row(status="CLOSED")
    state["view"] = role_view(status="CLOSED")

    response = client.post("/api/v1/tickets/1/close", json={"acknowledge": True})

    assert response.status_code == 200, response.text
    assert response.json()["data"]["ticket"]["available_actions"] == []


def test_user_confirming_resolution_gets_b_owned_actions_merged(api):
    client, _session, state = api
    state["actor"] = USER
    state["row"] = ticket_row(status="RESOLVED")
    state["view"] = role_view(status="RESOLVED", actions=("REOPEN", "CLOSE"))

    response = client.post("/api/v1/tickets/1/confirm-resolution")

    assert response.status_code == 200, response.text
    actions = response.json()["data"]["ticket"]["available_actions"]
    assert actions[:2] == ["REOPEN", "CLOSE"]
    assert "COMMENT" in actions and "UPLOAD_ATTACHMENT" in actions
    assert "EDIT" not in actions


def test_escalate_by_tier1_returns_200_then_scope_applies_again(api):
    """Agreed B/C: ESCALATE is the only action whose caller loses normal
    GET scope by acting. The action response must still be a 200 (the
    write is committed), with no actions and no vendor payload for Tier 1;
    a later GET is strictly scoped again."""
    client, session, state = api
    state["actor"] = TIER1
    # Post-write state: now assigned to the Tier 2 engineer (user 20).
    state["row"] = ticket_row(status="ASSIGNED", vendor_request_status="RESPONDED", assignee_id=20)
    state["view"] = role_view(
        status="ASSIGNED", vendor_request=RESPONDED_VENDOR_REQUEST, actions=("START",)
    )
    state["view"]["assignee"] = {
        "user_id": 20,
        "display_name": "Tier 2 Engineer",
        "tier": "TIER2",
        "skills": ["NETWORK"],
        "is_available": True,
        "active_load": 1,
    }

    response = client.post("/api/v1/tickets/1/escalate", json={"tier2_assignee_id": 20})

    assert response.status_code == 200, response.text
    assert session.committed is True
    assert state["authorized_calls"] == [True]
    data = response.json()["data"]
    assert data["action"] == "ESCALATE"
    assert data["ticket"]["status"] == "ASSIGNED"
    assert data["ticket"]["assignee"]["user_id"] == 20
    assert data["ticket"]["available_actions"] == []
    assert data["ticket"]["vendor_request"] is None
    assert data["vendor_request"] is None

    # A later GET by the former Tier 1 assignee is strictly scoped: 404.
    assert client.get("/api/v1/tickets/1").status_code == 404
    assert state["authorized_calls"][-1] is False

    # The new Tier 2 assignee sees it normally.
    state["actor"] = TIER2
    detail = client.get("/api/v1/tickets/1")
    assert detail.status_code == 200, detail.text
    assert "START" in detail.json()["data"]["available_actions"]
    assert detail.json()["data"]["vendor_request"]["vendor_request_id"] == 300


@pytest.mark.parametrize(("api_id", "suffix", "body", "expected", "action"), ACTIONS)
def test_only_escalate_skips_the_scope_check(api, api_id, suffix, body, expected, action):
    client, _session, state = api
    post_action(client, suffix, body)
    assert state["authorized_calls"] == [action == "ESCALATE"], api_id
