"""Unit tests for app.domains.workflow.serializer (C021).

Pure dataclasses/enums only -- no SQLAlchemy/Pydantic -- so, per this
project's established sandbox-verification convention, these are actually
*executed* (not merely syntax-checked) wherever the harness lacks pip
access, via a small pytest shim plus Python-3.11-stdlib shims
(``enum.StrEnum``, ``datetime.UTC``) for the 3.10 sandbox.
"""

import pytest

from app.core.enums import TicketStatus, UserRole
from app.domains.workflow.serializer import (
    ActorContext,
    build_ticket_state,
    build_ticket_workflow_view,
    derive_display_status,
    serialize_assignee,
    serialize_closure,
    serialize_pending_user,
    serialize_requester,
    serialize_resolution,
    serialize_sla,
    serialize_vendor_request,
)

USER = ActorContext(role=UserRole.USER, user_id=1)
TIER1 = ActorContext(role=UserRole.ENGINEER_TIER1, user_id=2)
TIER2 = ActorContext(role=UserRole.ENGINEER_TIER2, user_id=3)
MANAGER = ActorContext(role=UserRole.SERVICE_DESK_MANAGER, user_id=4)
VENDOR = ActorContext(role=UserRole.EXTERNAL_VENDOR, user_id=5, vendor_org_id=99)
OTHER_VENDOR = ActorContext(role=UserRole.EXTERNAL_VENDOR, user_id=6, vendor_org_id=100)


def base_raw(**overrides):
    raw = {
        "ticket_id": 1,
        "status_code": "ASSIGNED",
        "requester_id": 10,
        "requester_display_name": "Rita Requester",
        "assignee_id": 20,
        "assignee_user_id": 20,
        "assignee_display_name": "Eng Tier1",
        "assignee_role_code": "ENGINEER_TIER1",
        "assignee_is_available": 1,
        "assignee_skill_codes": "HARDWARE,NETWORK",
        "assignee_active_load": 3,
        "sla_cycle_no": 1,
        "sla_status_code": "ON_TRACK",
        "sla_started_at": "2026-09-01T00:00:00+00:00",
        "sla_deadline": "2026-09-03T00:00:00+00:00",
        "pending_user_reason": None,
        "pending_user_deadline": None,
        "resolution_summary": None,
        "resolution_type": None,
        "resolved_at": None,
        "auto_close_at": None,
        "closure_type": None,
        "closed_at": None,
    }
    raw.update(overrides)
    return raw


def base_vendor_row(**overrides):
    row = {
        "vendor_request_id": 500,
        "vendor_org_id": 99,
        "vendor_org_name": "Acme Networking",
        "vendor_org_is_active": 1,
        "vendor_message": "Please advise on switch firmware.",
        "status": "ACTIVE",
        "created_at": "2026-09-02T00:00:00+00:00",
        "responded_at": None,
    }
    row.update(overrides)
    return row


# ---------------------------------------------------------------------------
# derive_display_status
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", list(TicketStatus))
def test_internal_roles_see_the_raw_status_unchanged(status):
    for actor in (TIER1, TIER2, MANAGER):
        assert (
            derive_display_status(status, actor=actor, vendor_request_status=None) == status.value
        )


def test_user_pending_vendor_masks_to_in_progress():
    assert (
        derive_display_status(
            TicketStatus.PENDING_VENDOR, actor=USER, vendor_request_status="ACTIVE"
        )
        == "IN_PROGRESS"
    )


@pytest.mark.parametrize(
    "status", [s for s in TicketStatus if s is not TicketStatus.PENDING_VENDOR]
)
def test_user_sees_every_other_status_unchanged(status):
    assert derive_display_status(status, actor=USER, vendor_request_status=None) == status.value


def test_vendor_sees_pending_vendor_when_their_request_is_active():
    assert (
        derive_display_status(TicketStatus.ASSIGNED, actor=VENDOR, vendor_request_status="ACTIVE")
        == "PENDING_VENDOR"
    )


def test_vendor_sees_in_progress_once_their_request_is_responded():
    assert (
        derive_display_status(
            TicketStatus.IN_PROGRESS, actor=VENDOR, vendor_request_status="RESPONDED"
        )
        == "IN_PROGRESS"
    )


def test_vendor_sees_closed_regardless_of_vendor_request_status():
    assert (
        derive_display_status(TicketStatus.CLOSED, actor=VENDOR, vendor_request_status="RESPONDED")
        == "CLOSED"
    )


def test_vendor_workflow_view_masks_raw_status_in_both_status_fields():
    raw = base_raw(status_code="REOPENED")
    view = build_ticket_workflow_view(raw, base_vendor_row(status="RESPONDED"), actor=VENDOR)
    assert view["status"] == "IN_PROGRESS"
    assert view["display_status"] == "IN_PROGRESS"


# ---------------------------------------------------------------------------
# serialize_requester / serialize_assignee
# ---------------------------------------------------------------------------


def test_vendor_never_sees_requester_or_assignee():
    raw = base_raw()
    assert serialize_requester(raw, actor=VENDOR) is None
    assert serialize_assignee(raw, actor=VENDOR) is None


def test_other_roles_see_requester():
    raw = base_raw()
    for actor in (USER, TIER1, TIER2, MANAGER):
        assert serialize_requester(raw, actor=actor) == {
            "user_id": 10,
            "display_name": "Rita Requester",
        }


def test_assignee_summary_shape_when_assigned():
    raw = base_raw()
    for actor in (USER, TIER1, TIER2, MANAGER):
        assert serialize_assignee(raw, actor=actor) == {
            "user_id": 20,
            "display_name": "Eng Tier1",
            "tier": "TIER1",
            "skills": ["HARDWARE", "NETWORK"],
            "is_available": True,
            "active_load": 3,
        }


def test_assignee_is_null_when_unassigned():
    raw = base_raw(status_code="UNASSIGNED", assignee_id=None, assignee_user_id=None)
    assert serialize_assignee(raw, actor=MANAGER) is None


# ---------------------------------------------------------------------------
# serialize_sla / serialize_pending_user / serialize_resolution / serialize_closure
# ---------------------------------------------------------------------------


def test_vendor_gets_null_sla_pending_user_resolution_closure():
    raw = base_raw(
        pending_user_reason="INFORMATION_REQUIRED",
        pending_user_deadline="2026-09-05T00:00:00+00:00",
        resolution_summary="Fixed the switch.",
        resolution_type="USER_CONFIRMED",
        resolved_at="2026-09-04T00:00:00+00:00",
        auto_close_at="2026-09-11T00:00:00+00:00",
        closure_type="MANUAL_USER",
        closed_at="2026-09-06T00:00:00+00:00",
    )
    assert serialize_sla(raw, actor=VENDOR) is None
    assert serialize_pending_user(raw, actor=VENDOR) is None
    assert serialize_resolution(raw, actor=VENDOR) is None
    assert serialize_closure(raw, actor=VENDOR) is None


def test_sla_view_for_non_vendor_roles():
    raw = base_raw()
    assert serialize_sla(raw, actor=USER) == {
        "cycle_no": 1,
        "status": "ON_TRACK",
        "started_at": "2026-09-01T00:00:00+00:00",
        "deadline": "2026-09-03T00:00:00+00:00",
    }


def test_pending_user_view_present_only_when_pending():
    raw = base_raw()
    assert serialize_pending_user(raw, actor=USER) is None
    raw = base_raw(
        pending_user_reason="RESOLUTION_CONFIRMATION",
        pending_user_deadline="2026-09-10T00:00:00+00:00",
    )
    assert serialize_pending_user(raw, actor=USER) == {
        "reason": "RESOLUTION_CONFIRMATION",
        "deadline": "2026-09-10T00:00:00+00:00",
    }


def test_resolution_view_allows_null_type_while_confirmation_pending():
    raw = base_raw(
        resolution_summary="Fixed it.", resolution_type=None, resolved_at=None, auto_close_at=None
    )
    assert serialize_resolution(raw, actor=TIER1) == {
        "summary": "Fixed it.",
        "type": None,
        "resolved_at": None,
        "auto_close_at": None,
    }


def test_closure_view_present_only_once_closed():
    raw = base_raw()
    assert serialize_closure(raw, actor=MANAGER) is None
    raw = base_raw(closure_type="AUTO_AFTER_7_DAYS", closed_at="2026-09-12T00:00:00+00:00")
    assert serialize_closure(raw, actor=MANAGER) == {
        "type": "AUTO_AFTER_7_DAYS",
        "closed_at": "2026-09-12T00:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# serialize_vendor_request
# ---------------------------------------------------------------------------


def test_user_never_sees_vendor_request():
    assert serialize_vendor_request(base_vendor_row(), actor=USER) is None


def test_no_vendor_request_serializes_to_null():
    assert serialize_vendor_request(None, actor=MANAGER) is None


def test_internal_roles_see_full_vendor_request():
    row = base_vendor_row()
    for actor in (TIER1, TIER2, MANAGER):
        assert serialize_vendor_request(row, actor=actor) == {
            "vendor_request_id": 500,
            "vendor_org": {"vendor_org_id": 99, "name": "Acme Networking", "is_active": True},
            "status": "ACTIVE",
            "vendor_message": "Please advise on switch firmware.",
            "created_at": "2026-09-02T00:00:00+00:00",
            "responded_at": None,
        }


def test_vendor_sees_their_own_request():
    row = base_vendor_row()
    assert serialize_vendor_request(row, actor=VENDOR) is not None


def test_vendor_cannot_see_another_orgs_request():
    row = base_vendor_row()
    assert serialize_vendor_request(row, actor=OTHER_VENDOR) is None


# ---------------------------------------------------------------------------
# build_ticket_state / available_action_labels
# ---------------------------------------------------------------------------


def test_build_ticket_state_maps_raw_fields():
    raw = {**base_raw(), "has_active_vendor_request": True}
    state = build_ticket_state(raw)
    assert state.status is TicketStatus.ASSIGNED
    assert state.assignee_id == 20
    assert state.assignee_role is UserRole.ENGINEER_TIER1
    assert state.requester_id == 10
    assert state.pending_user_reason is None
    assert state.has_active_vendor_request is True


def test_closed_ticket_has_no_available_actions():
    raw = base_raw(
        status_code="CLOSED", closure_type="MANUAL_USER", closed_at="2026-09-06T00:00:00+00:00"
    )
    view = build_ticket_workflow_view(raw, None, actor=MANAGER)
    assert view["available_actions"] == []


def test_unassigned_ticket_offers_assign_only_to_manager():
    raw = base_raw(
        status_code="UNASSIGNED", assignee_id=None, assignee_user_id=None, assignee_role_code=None
    )
    manager_view = build_ticket_workflow_view(raw, None, actor=MANAGER)
    assert "ASSIGN" in manager_view["available_actions"]
    assert manager_view["available_actions"] == sorted(manager_view["available_actions"])
    tier1_view = build_ticket_workflow_view(raw, None, actor=TIER1)
    assert "ASSIGN" not in tier1_view["available_actions"]


def test_public_action_labels_never_include_non_workflow_actions():
    raw = base_raw(
        status_code="UNASSIGNED", assignee_id=None, assignee_user_id=None, assignee_role_code=None
    )
    view = build_ticket_workflow_view(raw, None, actor=MANAGER)
    assert "EDIT" not in view["available_actions"]
    assert "COMMENT" not in view["available_actions"]
    assert "UPLOAD_ATTACHMENT" not in view["available_actions"]


def test_build_ticket_workflow_view_full_shape_for_manager():
    raw = base_raw()
    view = build_ticket_workflow_view(raw, base_vendor_row(status="RESPONDED"), actor=MANAGER)
    assert set(view.keys()) == {
        "status",
        "display_status",
        "requester",
        "assignee",
        "sla",
        "pending_user",
        "resolution",
        "closure",
        "vendor_request",
        "available_actions",
    }
    assert view["status"] == "ASSIGNED"
    assert view["display_status"] == "ASSIGNED"
    assert view["vendor_request"]["status"] == "RESPONDED"


# ---------------------------------------------------------------------------
# VENDOR_RESPONSE contract agreed with B: only while the actor's own
# organisation holds the ACTIVE vendor request.
# ---------------------------------------------------------------------------


def pending_vendor_raw():
    return base_raw(status_code="PENDING_VENDOR", assignee_role_code="ENGINEER_TIER2")


def test_vendor_gets_vendor_response_while_own_org_request_is_active():
    view = build_ticket_workflow_view(pending_vendor_raw(), base_vendor_row(), actor=VENDOR)
    assert "VENDOR_RESPONSE" in view["available_actions"]


def test_vendor_gets_no_vendor_response_once_request_is_responded():
    row = base_vendor_row(status="RESPONDED", responded_at="2026-09-02T01:00:00+00:00")
    view = build_ticket_workflow_view(pending_vendor_raw(), row, actor=VENDOR)
    assert "VENDOR_RESPONSE" not in view["available_actions"]


def test_vendor_gets_no_vendor_response_without_any_request():
    view = build_ticket_workflow_view(pending_vendor_raw(), None, actor=VENDOR)
    assert "VENDOR_RESPONSE" not in view["available_actions"]


def test_vendor_gets_no_vendor_response_for_another_orgs_active_request():
    view = build_ticket_workflow_view(pending_vendor_raw(), base_vendor_row(), actor=OTHER_VENDOR)
    assert "VENDOR_RESPONSE" not in view["available_actions"]


def test_vendor_available_actions_never_include_b_owned_actions():
    view = build_ticket_workflow_view(pending_vendor_raw(), base_vendor_row(), actor=VENDOR)
    assert not {"EDIT", "COMMENT", "UPLOAD_ATTACHMENT"} & set(view["available_actions"])
