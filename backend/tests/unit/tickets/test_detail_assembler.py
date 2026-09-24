"""Coverage for the shared B-owned TicketDetail assembler."""

from datetime import datetime

from app.common.request_context import RequestContext
from app.core.enums import UserRole
from app.domains.tickets import detail_assembler


def _row(**overrides):
    row = {
        "ticket_id": 41,
        "title": "Printer unavailable",
        "description": "The third-floor printer is offline.",
        "category_code": "HARDWARE",
        "priority_code": "MEDIUM",
        "status_code": "PENDING_USER",
        "vendor_request_status": None,
        "created_at": datetime(2026, 9, 24, 1, 2, 3),
        "updated_at": datetime(2026, 9, 24, 2, 3, 4),
    }
    row.update(overrides)
    return row


def _workflow(**overrides):
    view = {
        "status": "PENDING_USER",
        "display_status": "PENDING_USER",
        "requester": {"user_id": 10, "display_name": "Requester"},
        "assignee": None,
        "sla": {
            "cycle_no": 1,
            "status": "PAUSED",
            "started_at": "2026-09-24T01:02:03+00:00",
            "deadline": None,
        },
        "pending_user": {
            "reason": "INFORMATION_REQUIRED",
            "deadline": "2026-09-29T01:02:03+00:00",
        },
        "resolution": None,
        "closure": None,
        "vendor_request": None,
        "available_actions": ["RESUME"],
    }
    view.update(overrides)
    return view


def test_assembler_returns_model_with_utc_times_and_merged_actions(monkeypatch):
    row = _row()

    class FakeTicketRepository:
        def __init__(self, _database):
            pass

        def detail(self, actor, ticket_id, *, visibility_already_authorized=False):
            assert visibility_already_authorized is False
            assert actor.user_id == 10
            assert ticket_id == 41
            return row

    class FakeWorkflowReadModel:
        def __init__(self, _database):
            pass

        def get_role_view(self, *, ticket_id, actor):
            assert ticket_id == 41
            assert actor.role is UserRole.USER
            return _workflow()

    monkeypatch.setattr(detail_assembler, "TicketRepository", FakeTicketRepository)
    monkeypatch.setattr(detail_assembler, "WorkflowReadModel", FakeWorkflowReadModel)

    detail = detail_assembler.assemble_ticket_detail(
        object(),
        actor=RequestContext(user_id=10, role=UserRole.USER),
        ticket_id=41,
    )

    assert detail is not None
    assert detail.created_at.isoformat() == "2026-09-24T01:02:03+00:00"
    assert detail.updated_at.isoformat() == "2026-09-24T02:03:04+00:00"
    assert [action.value for action in detail.available_actions] == [
        "RESUME",
        "UPLOAD_ATTACHMENT",
    ]


def test_vendor_only_gets_upload_for_own_active_request():
    actor = RequestContext(
        user_id=50,
        role=UserRole.EXTERNAL_VENDOR,
        vendor_org_id=7,
    )
    active = detail_assembler.merge_available_actions(
        actor,
        _row(status_code="PENDING_VENDOR", vendor_request_status="ACTIVE"),
        ["VENDOR_RESPONSE"],
    )
    responded = detail_assembler.merge_available_actions(
        actor,
        _row(status_code="PENDING_VENDOR", vendor_request_status="RESPONDED"),
        [],
    )

    assert [action.value for action in active] == [
        "VENDOR_RESPONSE",
        "UPLOAD_ATTACHMENT",
    ]
    assert responded == []


def test_tier1_cannot_read_vendor_request_payload(monkeypatch):
    vendor_request = {
        "vendor_request_id": 88,
        "vendor_org": {
            "vendor_org_id": 7,
            "name": "Hidden Vendor",
            "is_active": True,
        },
        "status": "RESPONDED",
        "vendor_message": "Sensitive vendor response",
        "created_at": "2026-09-24T01:02:03+00:00",
        "responded_at": "2026-09-24T02:03:04+00:00",
    }

    class FakeTicketRepository:
        def __init__(self, _database):
            pass

        def detail(self, _actor, _ticket_id, *, visibility_already_authorized=False):
            return _row(status_code="IN_PROGRESS")

    class FakeWorkflowReadModel:
        def __init__(self, _database):
            pass

        def get_role_view(self, *, ticket_id, actor):
            assert ticket_id == 41
            assert actor.role is UserRole.ENGINEER_TIER1
            return _workflow(
                status="IN_PROGRESS",
                display_status="IN_PROGRESS",
                pending_user=None,
                vendor_request=vendor_request,
                available_actions=["START"],
            )

    monkeypatch.setattr(detail_assembler, "TicketRepository", FakeTicketRepository)
    monkeypatch.setattr(detail_assembler, "WorkflowReadModel", FakeWorkflowReadModel)

    detail = detail_assembler.assemble_ticket_detail(
        object(),
        actor=RequestContext(user_id=20, role=UserRole.ENGINEER_TIER1),
        ticket_id=41,
    )

    assert detail is not None
    assert detail.vendor_request is None
