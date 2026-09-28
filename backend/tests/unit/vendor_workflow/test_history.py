"""Unit tests for the Q03 vendor history read (C047): role matrix, Vendor
organisation isolation, serialization and the SQL-level org filter."""

from datetime import datetime

import pytest

from app.common.request_context import RequestContext
from app.core.errors import ApplicationError
from app.domains.vendor_workflow.history import VendorHistoryReader, serialize_history_row
from app.domains.vendor_workflow.repository import VendorWorkflowRepository

USER = RequestContext(user_id=10, role="USER")
TIER1 = RequestContext(user_id=19, role="ENGINEER_TIER1")
TIER2 = RequestContext(user_id=20, role="ENGINEER_TIER2")
MANAGER = RequestContext(user_id=1, role="SERVICE_DESK_MANAGER")
VENDOR_A = RequestContext(user_id=40, role="EXTERNAL_VENDOR", vendor_org_id=7)
VENDOR_NO_ORG = RequestContext(user_id=41, role="EXTERNAL_VENDOR", vendor_org_id=None)


def history_row(**overrides):
    row = {
        "vendor_request_id": 300,
        "vendor_org_id": 7,
        "status": "RESPONDED",
        "vendor_message": "Please check the switch firmware.",
        "created_at": datetime(2026, 9, 1, 2, 0, 0),
        "responded_at": datetime(2026, 9, 1, 3, 0, 0),
        "vendor_org_name": "Acme Networks",
        "vendor_org_is_active": 1,
        "vendor_response_id": 400,
        "response_message": "Firmware 4.2.1 fixes it.",
        "response_created_at": datetime(2026, 9, 1, 3, 0, 0),
    }
    row.update(overrides)
    return row


class RepositoryFake:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.calls = []

    def list_request_history(self, *, ticket_id, vendor_org_id):
        self.calls.append({"ticket_id": ticket_id, "vendor_org_id": vendor_org_id})
        return self.rows


def reader_with(rows=()):
    reader = VendorHistoryReader(None)
    reader.repository = RepositoryFake(rows)
    return reader


@pytest.mark.parametrize("actor", [TIER2, MANAGER])
def test_internal_readers_get_every_organisation(actor):
    reader = reader_with([history_row()])
    result = reader.list_for_actor(ticket_id=1, actor=actor)
    assert reader.repository.calls == [{"ticket_id": 1, "vendor_org_id": None}]
    assert len(result) == 1


def test_vendor_is_isolated_to_own_organisation_in_the_query():
    reader = reader_with([history_row()])
    reader.list_for_actor(ticket_id=1, actor=VENDOR_A)
    assert reader.repository.calls == [{"ticket_id": 1, "vendor_org_id": 7}]


def test_vendor_without_organisation_fails_closed():
    reader = reader_with([history_row()])
    assert reader.list_for_actor(ticket_id=1, actor=VENDOR_NO_ORG) == []
    assert reader.repository.calls == []


@pytest.mark.parametrize("actor", [USER, TIER1])
def test_user_and_tier1_are_denied_without_touching_the_database(actor):
    reader = reader_with([history_row()])
    with pytest.raises(ApplicationError) as excinfo:
        reader.list_for_actor(ticket_id=1, actor=actor)
    assert excinfo.value.code == "DATA_SCOPE_DENIED"
    assert excinfo.value.status_code == 403
    assert reader.repository.calls == []


def test_serialized_row_has_request_and_response_in_utc():
    item = serialize_history_row(history_row())
    assert item["vendor_org"] == {"vendor_org_id": 7, "name": "Acme Networks", "is_active": True}
    assert item["created_at"].isoformat() == "2026-09-01T02:00:00+00:00"
    assert item["responded_at"].isoformat() == "2026-09-01T03:00:00+00:00"
    assert item["response"] == {
        "vendor_response_id": 400,
        "vendor_request_id": 300,
        "message": "Firmware 4.2.1 fixes it.",
        "created_at": item["response"]["created_at"],
    }
    assert item["response"]["created_at"].isoformat() == "2026-09-01T03:00:00+00:00"


def test_unanswered_request_has_null_response():
    item = serialize_history_row(
        history_row(
            status="ACTIVE",
            responded_at=None,
            vendor_response_id=None,
            response_message=None,
            response_created_at=None,
        )
    )
    assert item["status"] == "ACTIVE"
    assert item["responded_at"] is None
    assert item["response"] is None


def test_serialized_row_exposes_no_internal_user_fields():
    item = serialize_history_row(history_row())
    assert set(item) == {
        "vendor_request_id",
        "vendor_org",
        "status",
        "vendor_message",
        "created_at",
        "responded_at",
        "response",
    }


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

            def all(self):
                return []

        return _Result()


def test_repository_filters_by_organisation_in_sql():
    database = _CapturingDatabase()
    VendorWorkflowRepository(database).list_request_history(ticket_id=1, vendor_org_id=7)
    assert "vr.vendor_org_id = :vendor_org_id" in database.sql
    assert "ORDER BY vr.created_at, vr.vendor_request_id" in database.sql
    assert database.params == {"ticket_id": 1, "vendor_org_id": 7}


def test_repository_without_organisation_has_no_org_filter():
    database = _CapturingDatabase()
    VendorWorkflowRepository(database).list_request_history(ticket_id=1, vendor_org_id=None)
    assert ":vendor_org_id" not in database.sql
    assert database.params == {"ticket_id": 1}
