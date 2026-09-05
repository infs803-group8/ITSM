from datetime import UTC, datetime

import pytest

from app.common.request_context import RequestContext
from app.core.enums import EventScope, EventType, UserRole
from app.core.errors import ApplicationError
from app.domains.audit.access_policy import TicketAccessRecord
from app.domains.audit.service import AuditService


class AuditRepositoryFake:
    def __init__(self, *, ticket=None, rows=None, total=0):
        self.ticket = ticket
        self.rows = rows or []
        self.total = total
        self.append_calls: list[dict] = []
        self.list_calls: list[dict] = []

    def get_ticket_access(self, ticket_id, actor):
        return self.ticket

    def append(self, **kwargs):
        self.append_calls.append(kwargs)

    def list_events(self, **kwargs):
        self.list_calls.append(kwargs)
        return self.rows, self.total


def ticket(**overrides) -> TicketAccessRecord:
    values = {
        "ticket_id": 5001,
        "requester_id": 1001,
        "assignee_id": 2001,
        "status_code": "IN_PROGRESS",
        "active_vendor_request_id": None,
        "active_vendor_org_id": None,
        "actor_has_vendor_history": False,
    }
    values.update(overrides)
    return TicketAccessRecord(**values)


def event_row(**overrides):
    values = {
        "event_id": 9001,
        "ticket_id": 5001,
        "event_type": "TICKET_CREATED",
        "scope": "USER_VISIBLE",
        "actor_id": 1001,
        "actor_display_name": "Example Requester",
        "actor_role": "USER",
        "cycle_no": 1,
        "occurred_at": datetime(2026, 9, 1, 1, 0, 0, tzinfo=UTC),
        "metadata": {},
    }
    values.update(overrides)
    return values


def audit_service(**repository_kwargs) -> tuple[AuditService, AuditRepositoryFake]:
    service = AuditService(None)
    fake = AuditRepositoryFake(**repository_kwargs)
    service.repository = fake
    return service, fake


def test_append_event_forwards_enum_values_to_the_repository():
    service, fake = audit_service()
    service.append_event(
        ticket_id=5001,
        event_type=EventType.HANDLING_STARTED,
        scope=EventScope.USER_VISIBLE,
        actor_id=2001,
        metadata={"note": "started"},
    )
    assert len(fake.append_calls) == 1
    call = fake.append_calls[0]
    assert call["event_type"] == "HANDLING_STARTED"
    assert call["scope"] == "USER_VISIBLE"
    assert call["actor_id"] == 2001
    assert call["metadata"] == {"note": "started"}


def test_hidden_ticket_is_reported_as_not_found():
    service, _fake = audit_service(ticket=None)
    actor = RequestContext(user_id=1001, role=UserRole.USER)
    with pytest.raises(ApplicationError) as error:
        service.list_events(
            5001, actor, event_type=None, scope=None, page=1, page_size=20
        )
    assert error.value.code == "RESOURCE_NOT_FOUND"


def test_list_events_maps_rows_into_the_response_schema():
    service, fake = audit_service(
        ticket=ticket(), rows=[event_row()], total=1
    )
    actor = RequestContext(user_id=1001, role=UserRole.USER)
    response = service.list_events(
        5001, actor, event_type=None, scope=None, page=1, page_size=20
    )
    assert response.meta.total == 1
    assert len(response.data) == 1
    item = response.data[0]
    assert item.event_id == 9001
    assert item.event_type == EventType.TICKET_CREATED
    assert item.scope == EventScope.USER_VISIBLE
    assert item.actor is not None
    assert item.actor.display_name == "Example Requester"
    assert item.actor.role == UserRole.USER


def test_list_events_maps_a_system_generated_row_to_a_null_actor():
    service, fake = audit_service(
        ticket=ticket(),
        rows=[
            event_row(
                event_id=9002,
                event_type="SLA_CYCLE_STARTED",
                actor_id=None,
                actor_display_name=None,
                actor_role=None,
            )
        ],
        total=1,
    )
    actor = RequestContext(user_id=1001, role=UserRole.USER)
    response = service.list_events(
        5001, actor, event_type=None, scope=None, page=1, page_size=20
    )
    assert response.data[0].actor is None


def test_list_events_decodes_json_string_metadata():
    service, fake = audit_service(
        ticket=ticket(),
        rows=[event_row(metadata='{"reason": "ESCALATION"}')],
        total=1,
    )
    actor = RequestContext(user_id=1001, role=UserRole.USER)
    response = service.list_events(
        5001, actor, event_type=None, scope=None, page=1, page_size=20
    )
    assert response.data[0].metadata == {"reason": "ESCALATION"}


def test_list_events_restricts_scope_filter_for_user_role():
    service, fake = audit_service(ticket=ticket(), rows=[], total=0)
    actor = RequestContext(user_id=1001, role=UserRole.USER)
    service.list_events(
        5001, actor, event_type=None, scope=None, page=1, page_size=20
    )
    assert fake.list_calls[0]["allowed_scopes"] == ["USER_VISIBLE"]
    assert fake.list_calls[0]["vendor_org_id"] is None


def test_list_events_passes_the_actors_own_vendor_org_id_for_vendor_scope():
    service, fake = audit_service(
        ticket=ticket(active_vendor_request_id=1, active_vendor_org_id=7,
                       actor_has_vendor_history=True),
        rows=[],
        total=0,
    )
    actor = RequestContext(user_id=3001, role=UserRole.EXTERNAL_VENDOR, vendor_org_id=7)
    service.list_events(
        5001, actor, event_type=None, scope=None, page=1, page_size=20
    )
    assert fake.list_calls[0]["vendor_org_id"] == 7
    assert fake.list_calls[0]["allowed_scopes"] == ["VENDOR_SCOPE"]


def test_list_events_rejects_a_scope_the_role_cannot_read():
    service, fake = audit_service(ticket=ticket(), rows=[], total=0)
    actor = RequestContext(user_id=1001, role=UserRole.USER)
    with pytest.raises(ApplicationError) as error:
        service.list_events(
            5001,
            actor,
            event_type=None,
            scope=EventScope.INTERNAL_ONLY,
            page=1,
            page_size=20,
        )
    assert error.value.code == "DATA_SCOPE_DENIED"
