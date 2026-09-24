"""``visibility_already_authorized`` on the shared TicketDetail assembler
(agreed B/C for PR-2): only the post-write ESCALATE response may skip the
repository's ticket-level scope check; nothing else changes."""

from datetime import datetime

from app.common.request_context import RequestContext
from app.core.enums import UserRole
from app.domains.tickets import detail_assembler
from app.domains.tickets.repository import TicketRepository

TIER1 = RequestContext(user_id=19, role=UserRole.ENGINEER_TIER1)
MANAGER = RequestContext(user_id=1, role=UserRole.SERVICE_DESK_MANAGER)
VENDOR = RequestContext(user_id=40, role=UserRole.EXTERNAL_VENDOR, vendor_org_id=7)

VENDOR_REQUEST = {
    "vendor_request_id": 300,
    "vendor_org": {"vendor_org_id": 7, "name": "Acme", "is_active": True},
    "status": "RESPONDED",
    "vendor_message": "Please check.",
    "created_at": "2026-09-01T02:00:00+00:00",
    "responded_at": "2026-09-01T03:00:00+00:00",
}


def _row():
    # After ESCALATE: assigned to Tier 2 (user 20), no longer to Tier 1 (19).
    return {
        "ticket_id": 1,
        "title": "VPN drops",
        "description": "Every hour.",
        "category_code": "NETWORK",
        "priority_code": "HIGH",
        "status_code": "ASSIGNED",
        "assignee_id": 20,
        "vendor_request_status": "RESPONDED",
        "created_at": datetime(2026, 9, 1, 0, 0, 0),
        "updated_at": datetime(2026, 9, 1, 1, 0, 0),
    }


def _workflow(actions=("START",)):
    return {
        "status": "ASSIGNED",
        "display_status": "ASSIGNED",
        "requester": {"user_id": 10, "display_name": "Requester"},
        "assignee": None,
        "sla": None,
        "pending_user": None,
        "resolution": None,
        "closure": None,
        "vendor_request": VENDOR_REQUEST,
        "available_actions": list(actions),
    }


def _install_fakes(monkeypatch, calls, workflow_actions=("START",)):
    """Repository fake that applies engineer scope the way the real
    ``TicketRepository.scope_sql`` does (assignee_id = actor)."""

    def in_scope(actor):
        if actor.role == UserRole.SERVICE_DESK_MANAGER:
            return True
        return _row()["assignee_id"] == actor.user_id

    class FakeTicketRepository:
        def __init__(self, _database):
            pass

        def detail(self, actor, ticket_id, *, visibility_already_authorized=False):
            calls.append(visibility_already_authorized)
            if not visibility_already_authorized and not in_scope(actor):
                return None
            return _row()

        def visible(self, actor, ticket_id):
            return in_scope(actor)

    class FakeWorkflowReadModel:
        def __init__(self, _database):
            pass

        def get_role_view(self, *, ticket_id, actor):
            return _workflow(workflow_actions)

    monkeypatch.setattr(detail_assembler, "TicketRepository", FakeTicketRepository)
    monkeypatch.setattr(detail_assembler, "WorkflowReadModel", FakeWorkflowReadModel)


def test_default_call_cannot_bypass_scope(monkeypatch):
    calls = []
    _install_fakes(monkeypatch, calls)
    detail = detail_assembler.assemble_ticket_detail(object(), actor=TIER1, ticket_id=1)
    assert detail is None
    assert calls == [False]


def test_authorized_out_of_scope_actor_gets_detail_with_no_actions(monkeypatch):
    calls = []
    # Even if the workflow slice offered something, an actor who has lost
    # normal scope must get no actions at all.
    _install_fakes(monkeypatch, calls, workflow_actions=("START",))
    detail = detail_assembler.assemble_ticket_detail(
        object(), actor=TIER1, ticket_id=1, visibility_already_authorized=True
    )
    assert detail is not None
    assert calls == [True]
    assert detail.available_actions == []
    # Field-level role filtering is not skipped: Tier 1 never sees it.
    assert detail.vendor_request is None
    assert detail.description == "Every hour."


def test_authorized_actor_still_in_scope_keeps_normal_actions(monkeypatch):
    calls = []
    _install_fakes(monkeypatch, calls, workflow_actions=("ASSIGN",))
    detail = detail_assembler.assemble_ticket_detail(
        object(), actor=MANAGER, ticket_id=1, visibility_already_authorized=True
    )
    assert [a.value for a in detail.available_actions] == [
        "ASSIGN",
        "COMMENT",
        "UPLOAD_ATTACHMENT",
        "EDIT",
    ]
    assert detail.vendor_request is not None


class _CapturingDatabase:
    def __init__(self):
        self.sql = None
        self.params = None

    def execute(self, statement, params):
        self.sql = str(statement)
        self.params = params

        class _Result:
            def mappings(self):
                return self

            def one_or_none(self):
                return None

        return _Result()


def test_repository_detail_is_scoped_by_default():
    database = _CapturingDatabase()
    TicketRepository(database).detail(TIER1, 1)
    assert "t.assignee_id = :actor_id" in database.sql
    assert database.params == {"actor_id": 19, "ticket_id": 1}


def test_repository_detail_skips_only_ticket_scope_when_authorized():
    database = _CapturingDatabase()
    TicketRepository(database).detail(TIER1, 1, visibility_already_authorized=True)
    assert ":actor_id" not in database.sql
    assert "WHERE t.ticket_id=:ticket_id AND 1 = 1" in database.sql
    assert database.params == {"ticket_id": 1}


def test_repository_keeps_vendor_org_filter_when_authorized():
    database = _CapturingDatabase()
    TicketRepository(database).detail(VENDOR, 1, visibility_already_authorized=True)
    assert "vr2.vendor_org_id = :vendor_org_id" in database.sql
    assert database.params == {"vendor_org_id": 7, "ticket_id": 1}
