"""Real-MySQL coverage for the API-32 audit event domain (PR #21, R21-02).

The existing unit tests in ``tests/unit/audit/test_service.py`` use a fake
repository (pure Python objects, no SQL at all) plus, in a couple of
cases, an in-memory SQLite fixture. Neither proves the things that only a
real MySQL 8.4 server -- the one this project actually deploys against --
can prove: that the ``metadata`` JSON column round-trips through
SQLAlchemy's MySQL dialect the way the service expects, that the
``uq_ticket_events_cycle_guard`` unique key really rejects a duplicate
SLA-cycle write with ``IntegrityError`` rather than silently succeeding,
that ``AuditRepository.append()`` really never commits on its own (so a
caller's rollback really discards it), and that the hand-written scope /
vendor-isolation SQL in ``AuditRepository.list_events`` behaves correctly
against InnoDB rather than SQLite's more permissive type/locking model.

Run only against a disposable schema, same convention as
``test_member_a_mysql.py``:

    RUN_MYSQL_INTEGRATION=1 pytest tests/integration/test_audit_mysql.py

Ticket ids 80001-80010 are reserved for this file so it can share the one
disposable schema ``scripts/run_mysql_integration.py`` provisions with
every other integration test file in the same CI run without colliding
with their fixture rows. Nothing here ever deletes from ``ticket_events``:
the canonical schema makes it append-only via a DB trigger (see
``test_create_assignment.py`` for the same lesson learned the hard way),
and every test below already uses its own reserved ticket id, so leaving
old rows in place cannot leak into a later test's assertions -- every
query in this module is filtered by ``ticket_id``.
"""

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.common.request_context import RequestContext
from app.core.config import get_settings
from app.core.enums import EventScope, EventType, UserRole
from app.core.errors import ApplicationError
from app.domains.audit.repository import AuditRepository
from app.domains.audit.service import AuditService

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MYSQL_INTEGRATION") != "1",
    reason="Requires a disposable local MySQL integration schema.",
)


def _engine():
    settings = get_settings()
    assert settings.database_url.endswith("/service_desk_member_a_test")
    return create_engine(settings.database_url)


def _seed_user(
    engine,
    *,
    user_id: int,
    email: str,
    role_code: str,
    display_name: str = "Test User",
    vendor_org_id: int | None = None,
    is_available: bool | None = None,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO users
                  (user_id, email, password_hash, display_name, role_code,
                   is_available, vendor_org_id)
                VALUES
                  (:user_id, :email, 'x', :display_name, :role_code,
                   :is_available, :vendor_org_id)
                """
            ),
            {
                "user_id": user_id,
                "email": email,
                "display_name": display_name,
                "role_code": role_code,
                "is_available": is_available,
                "vendor_org_id": vendor_org_id,
            },
        )


def _seed_vendor_org(engine, *, vendor_org_id: int, name: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO vendor_organisations (vendor_org_id, name) VALUES (:id, :name)"),
            {"id": vendor_org_id, "name": name},
        )


def _seed_ticket(engine, *, ticket_id: int, requester_id: int, assignee_id: int | None) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO tickets
                  (ticket_id, requester_id, title, description, category_code,
                   priority_code, status_code, assignee_id)
                VALUES
                  (:ticket_id, :requester_id, 'Audit integration ticket',
                   'Seeded for PR #21 R21-02', 'NETWORK', 'MEDIUM',
                   CASE WHEN :assignee_id IS NULL THEN 'NEW' ELSE 'ASSIGNED' END,
                   :assignee_id)
                """
            ),
            {"ticket_id": ticket_id, "requester_id": requester_id, "assignee_id": assignee_id},
        )


def _seed_vendor_request(
    engine,
    *,
    vendor_request_id: int,
    ticket_id: int,
    vendor_org_id: int,
    requested_by_id: int,
    status: str,
    responded_at: datetime | None = None,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO vendor_requests
                  (vendor_request_id, ticket_id, vendor_org_id, requested_by_id,
                   vendor_message, status, responded_at)
                VALUES
                  (:id, :ticket_id, :vendor_org_id, :requested_by_id,
                   'Vendor-safe message body', :status, :responded_at)
                """
            ),
            {
                "id": vendor_request_id,
                "ticket_id": ticket_id,
                "vendor_org_id": vendor_org_id,
                "requested_by_id": requested_by_id,
                "status": status,
                "responded_at": responded_at,
            },
        )


def _append_event(engine, **kwargs) -> int:
    """Write one event through the real repository/service and commit.

    Used for fixture setup (as opposed to the transaction-boundary tests
    below, which call ``AuditRepository.append`` directly so they control
    the commit/rollback themselves).
    """
    with Session(engine) as database:
        event = AuditRepository(database).append(**kwargs)
        database.commit()
        return event.event_id


def _list(engine, ticket_id, actor, *, event_type=None, scope=None, page=1, page_size=20):
    with Session(engine) as database:
        return AuditService(database).list_events(
            ticket_id, actor, event_type=event_type, scope=scope, page=page, page_size=page_size
        )


# ---------------------------------------------------------------------------
# Row 1: User / Tier 1 / Tier 2 / Manager each only see their own ticket
# scope and their own allowed EventScopes.
# ---------------------------------------------------------------------------


def test_each_role_sees_only_its_own_ticket_scope_and_event_scopes():
    engine = _engine()
    requester = 80101
    tier1 = 80102
    tier2 = 80103
    manager = 80104
    _seed_user(engine, user_id=requester, email="requester-audit1@test.local", role_code="USER")
    _seed_user(
        engine,
        user_id=tier1,
        email="tier1-audit1@test.local",
        role_code="ENGINEER_TIER1",
        is_available=True,
    )
    _seed_user(
        engine,
        user_id=tier2,
        email="tier2-audit1@test.local",
        role_code="ENGINEER_TIER2",
        is_available=True,
    )
    _seed_user(
        engine, user_id=manager, email="manager-audit1@test.local", role_code="SERVICE_DESK_MANAGER"
    )
    vendor_org = 80105
    _seed_vendor_org(engine, vendor_org_id=vendor_org, name="Audit R1 Vendor Org")

    ticket_tier1 = 80001
    ticket_tier2 = 80002
    _seed_ticket(engine, ticket_id=ticket_tier1, requester_id=requester, assignee_id=tier1)
    _seed_ticket(engine, ticket_id=ticket_tier2, requester_id=requester, assignee_id=tier2)

    for ticket_id in (ticket_tier1, ticket_tier2):
        _append_event(
            engine,
            ticket_id=ticket_id,
            event_type=EventType.TICKET_CREATED,
            scope=EventScope.USER_VISIBLE,
            actor_id=requester,
        )
        _append_event(
            engine,
            ticket_id=ticket_id,
            event_type=EventType.HANDLING_STARTED,
            scope=EventScope.INTERNAL_ONLY,
            actor_id=tier1 if ticket_id == ticket_tier1 else tier2,
        )
        _append_event(
            engine,
            ticket_id=ticket_id,
            event_type=EventType.VENDOR_REQUESTED,
            scope=EventScope.VENDOR_SCOPE,
            actor_id=tier2 if ticket_id == ticket_tier1 else tier1,
            vendor_org_id=vendor_org,
        )

    user_ctx = RequestContext(user_id=requester, role=UserRole.USER)
    response = _list(engine, ticket_tier1, user_ctx)
    assert {item.scope for item in response.data} == {EventScope.USER_VISIBLE}
    assert response.meta.total == 1

    tier1_ctx = RequestContext(user_id=tier1, role=UserRole.ENGINEER_TIER1)
    response = _list(engine, ticket_tier1, tier1_ctx)
    assert {item.scope for item in response.data} == {
        EventScope.USER_VISIBLE,
        EventScope.INTERNAL_ONLY,
    }
    assert response.meta.total == 2

    tier2_ctx = RequestContext(user_id=tier2, role=UserRole.ENGINEER_TIER2)
    response = _list(engine, ticket_tier2, tier2_ctx)
    assert {item.scope for item in response.data} == {
        EventScope.USER_VISIBLE,
        EventScope.INTERNAL_ONLY,
        EventScope.VENDOR_SCOPE,
    }
    assert response.meta.total == 3

    manager_ctx = RequestContext(user_id=manager, role=UserRole.SERVICE_DESK_MANAGER)
    response = _list(engine, ticket_tier1, manager_ctx)
    assert response.meta.total == 3

    # Tier 1 is not the assignee of ticket_tier2 -> hidden as 404, same as
    # any other actor who is not entitled to read this ticket at all.
    with pytest.raises(ApplicationError) as error:
        _list(engine, ticket_tier2, tier1_ctx)
    assert error.value.code == "RESOURCE_NOT_FOUND"


# ---------------------------------------------------------------------------
# Row 2: a historical vendor and the current active vendor each only read
# their own organisation's VENDOR_SCOPE events.
# ---------------------------------------------------------------------------


def test_historical_and_active_vendors_are_isolated_to_their_own_org_events():
    engine = _engine()
    requester = 80201
    tier2 = 80202
    vendor_a_user = 80203
    vendor_b_user = 80204
    vendor_org_a = 80205
    vendor_org_b = 80206
    _seed_user(engine, user_id=requester, email="requester-audit2@test.local", role_code="USER")
    _seed_user(
        engine,
        user_id=tier2,
        email="tier2-audit2@test.local",
        role_code="ENGINEER_TIER2",
        is_available=True,
    )
    _seed_vendor_org(engine, vendor_org_id=vendor_org_a, name="Audit R2 Vendor Org A")
    _seed_vendor_org(engine, vendor_org_id=vendor_org_b, name="Audit R2 Vendor Org B")
    _seed_user(
        engine,
        user_id=vendor_a_user,
        email="vendor-a-audit2@test.local",
        role_code="EXTERNAL_VENDOR",
        vendor_org_id=vendor_org_a,
    )
    _seed_user(
        engine,
        user_id=vendor_b_user,
        email="vendor-b-audit2@test.local",
        role_code="EXTERNAL_VENDOR",
        vendor_org_id=vendor_org_b,
    )

    ticket_id = 80003
    _seed_ticket(engine, ticket_id=ticket_id, requester_id=requester, assignee_id=tier2)
    # Vendor A's request was cancelled (history); Vendor B's is the current
    # active one. Both should still be readable per R21-01's rule that
    # historical-vendor read access does not require an ACTIVE request.
    _seed_vendor_request(
        engine,
        vendor_request_id=80207,
        ticket_id=ticket_id,
        vendor_org_id=vendor_org_a,
        requested_by_id=tier2,
        status="CANCELLED",
    )
    _seed_vendor_request(
        engine,
        vendor_request_id=80208,
        ticket_id=ticket_id,
        vendor_org_id=vendor_org_b,
        requested_by_id=tier2,
        status="ACTIVE",
    )
    _append_event(
        engine,
        ticket_id=ticket_id,
        event_type=EventType.VENDOR_RESPONDED,
        scope=EventScope.VENDOR_SCOPE,
        actor_id=vendor_a_user,
        vendor_org_id=vendor_org_a,
    )
    _append_event(
        engine,
        ticket_id=ticket_id,
        event_type=EventType.VENDOR_REQUESTED,
        scope=EventScope.VENDOR_SCOPE,
        actor_id=tier2,
        vendor_org_id=vendor_org_b,
    )

    vendor_a_ctx = RequestContext(
        user_id=vendor_a_user, role=UserRole.EXTERNAL_VENDOR, vendor_org_id=vendor_org_a
    )
    response = _list(engine, ticket_id, vendor_a_ctx)
    assert response.meta.total == 1
    assert response.data[0].event_type == EventType.VENDOR_RESPONDED

    vendor_b_ctx = RequestContext(
        user_id=vendor_b_user, role=UserRole.EXTERNAL_VENDOR, vendor_org_id=vendor_org_b
    )
    response = _list(engine, ticket_id, vendor_b_ctx)
    assert response.meta.total == 1
    assert response.data[0].event_type == EventType.VENDOR_REQUESTED


# ---------------------------------------------------------------------------
# Row 3: a vendor with no request history on this ticket at all gets 404.
# ---------------------------------------------------------------------------


def test_vendor_with_no_organisation_history_on_the_ticket_gets_404():
    engine = _engine()
    requester = 80301
    outsider_vendor_user = 80302
    outsider_org = 80303
    _seed_user(engine, user_id=requester, email="requester-audit3@test.local", role_code="USER")
    _seed_vendor_org(engine, vendor_org_id=outsider_org, name="Audit R3 Outsider Org")
    _seed_user(
        engine,
        user_id=outsider_vendor_user,
        email="vendor-outsider-audit3@test.local",
        role_code="EXTERNAL_VENDOR",
        vendor_org_id=outsider_org,
    )
    ticket_id = 80004
    _seed_ticket(engine, ticket_id=ticket_id, requester_id=requester, assignee_id=None)

    outsider_ctx = RequestContext(
        user_id=outsider_vendor_user, role=UserRole.EXTERNAL_VENDOR, vendor_org_id=outsider_org
    )
    with pytest.raises(ApplicationError) as error:
        _list(engine, ticket_id, outsider_ctx)
    assert error.value.code == "RESOURCE_NOT_FOUND"


# ---------------------------------------------------------------------------
# Row 4: explicitly requesting a scope the role cannot read -> 403.
# ---------------------------------------------------------------------------


def test_explicitly_requesting_an_unauthorised_scope_is_403():
    engine = _engine()
    requester = 80401
    _seed_user(engine, user_id=requester, email="requester-audit4@test.local", role_code="USER")
    ticket_id = 80005
    _seed_ticket(engine, ticket_id=ticket_id, requester_id=requester, assignee_id=None)

    user_ctx = RequestContext(user_id=requester, role=UserRole.USER)
    with pytest.raises(ApplicationError) as error:
        _list(engine, ticket_id, user_ctx, scope=EventScope.INTERNAL_ONLY)
    assert error.value.code == "DATA_SCOPE_DENIED"


# ---------------------------------------------------------------------------
# Row 5: pagination is stable across ties, has no duplicates/gaps, and
# ``total`` only counts events inside the caller's allowed scopes.
# ---------------------------------------------------------------------------


def test_pagination_is_stable_and_total_only_counts_authorised_scopes():
    engine = _engine()
    requester = 80501
    _seed_user(engine, user_id=requester, email="requester-audit5@test.local", role_code="USER")
    ticket_id = 80006
    _seed_ticket(engine, ticket_id=ticket_id, requester_id=requester, assignee_id=None)

    tied_time = datetime(2026, 9, 1, 12, 0, 0, tzinfo=UTC)
    user_visible_ids = [
        _append_event(
            engine,
            ticket_id=ticket_id,
            event_type=EventType.HANDLING_STARTED,
            scope=EventScope.USER_VISIBLE,
            actor_id=requester,
            occurred_at=tied_time,
        )
        for _ in range(5)
    ]
    # A couple of INTERNAL_ONLY events the requester cannot see at all --
    # these must never appear in the paginated results or the total.
    _append_event(
        engine,
        ticket_id=ticket_id,
        event_type=EventType.HANDLING_STARTED,
        scope=EventScope.INTERNAL_ONLY,
        actor_id=None,
        occurred_at=tied_time,
    )
    _append_event(
        engine,
        ticket_id=ticket_id,
        event_type=EventType.HANDLING_STARTED,
        scope=EventScope.INTERNAL_ONLY,
        actor_id=None,
        occurred_at=tied_time,
    )

    user_ctx = RequestContext(user_id=requester, role=UserRole.USER)
    seen_event_ids: list[int] = []
    page_size = 2
    total_pages = None
    page = 1
    while True:
        response = _list(engine, ticket_id, user_ctx, page=page, page_size=page_size)
        if total_pages is None:
            total_pages = response.meta.total_pages
            assert response.meta.total == 5
            assert total_pages == 3
        seen_event_ids.extend(item.event_id for item in response.data)
        assert all(item.scope == EventScope.USER_VISIBLE for item in response.data)
        if page >= total_pages:
            break
        page += 1

    assert sorted(seen_event_ids) == sorted(user_visible_ids)
    assert len(seen_event_ids) == len(set(seen_event_ids)), "pagination produced a duplicate row"


# ---------------------------------------------------------------------------
# Row 6: JSON metadata round-trips as a dict through the real MySQL JSON
# column, and a system-generated event (actor_id NULL) maps to actor=None.
# ---------------------------------------------------------------------------


def test_json_metadata_and_a_system_generated_event_map_correctly():
    engine = _engine()
    requester = 80601
    _seed_user(engine, user_id=requester, email="requester-audit6@test.local", role_code="USER")
    ticket_id = 80007
    _seed_ticket(engine, ticket_id=ticket_id, requester_id=requester, assignee_id=None)

    metadata = {"reason": "ESCALATION", "previous_tier": "ENGINEER_TIER1", "count": 2}
    _append_event(
        engine,
        ticket_id=ticket_id,
        event_type=EventType.SLA_AT_RISK,
        scope=EventScope.USER_VISIBLE,
        actor_id=None,
        cycle_no=1,
        metadata=metadata,
    )

    user_ctx = RequestContext(user_id=requester, role=UserRole.USER)
    response = _list(engine, ticket_id, user_ctx)
    assert response.meta.total == 1
    item = response.data[0]
    assert item.actor is None
    assert isinstance(item.metadata, dict)
    assert item.metadata == metadata
    # Round-tripping through MySQL's JSON type must not reorder, stringify
    # or drop any key -- this is exactly what an in-memory SQLite fixture
    # cannot prove, since SQLite has no native JSON column type.
    assert set(item.metadata.keys()) == {"reason", "previous_tier", "count"}


# ---------------------------------------------------------------------------
# Row 7: a caller-side rollback discards both the business-data change and
# the event append() staged in the same transaction.
# ---------------------------------------------------------------------------


def test_a_callers_rollback_discards_both_the_ticket_update_and_the_event():
    engine = _engine()
    requester = 80701
    tier1 = 80702
    _seed_user(engine, user_id=requester, email="requester-audit7@test.local", role_code="USER")
    _seed_user(
        engine,
        user_id=tier1,
        email="tier1-audit7@test.local",
        role_code="ENGINEER_TIER1",
        is_available=True,
    )
    ticket_id = 80008
    _seed_ticket(engine, ticket_id=ticket_id, requester_id=requester, assignee_id=tier1)

    with Session(engine) as database:
        database.execute(
            text("UPDATE tickets SET status_code = 'IN_PROGRESS' WHERE ticket_id = :id"),
            {"id": ticket_id},
        )
        AuditRepository(database).append(
            ticket_id=ticket_id,
            event_type=EventType.HANDLING_STARTED.value,
            scope=EventScope.INTERNAL_ONLY.value,
            actor_id=tier1,
        )
        database.rollback()

    with engine.connect() as connection:
        status = connection.execute(
            text("SELECT status_code FROM tickets WHERE ticket_id = :id"), {"id": ticket_id}
        ).scalar_one()
        event_count = connection.execute(
            text("SELECT COUNT(*) FROM ticket_events WHERE ticket_id = :id"), {"id": ticket_id}
        ).scalar_one()
    assert status == "NEW"
    assert event_count == 0


# ---------------------------------------------------------------------------
# Row 8: append() itself never commits -- the event is invisible to a
# second connection until the caller commits, at which point it appears.
# ---------------------------------------------------------------------------


def test_append_does_not_commit_until_the_caller_does():
    engine = _engine()
    requester = 80801
    _seed_user(engine, user_id=requester, email="requester-audit8@test.local", role_code="USER")
    ticket_id = 80009
    _seed_ticket(engine, ticket_id=ticket_id, requester_id=requester, assignee_id=None)

    with Session(engine) as database:
        AuditRepository(database).append(
            ticket_id=ticket_id,
            event_type=EventType.TICKET_CREATED.value,
            scope=EventScope.USER_VISIBLE.value,
            actor_id=requester,
        )
        # Not committed yet: a completely separate connection must see
        # nothing, proving AuditRepository.append() only adds+flushes and
        # never commits on the caller's behalf.
        with engine.connect() as other_connection:
            mid_transaction_count = other_connection.execute(
                text("SELECT COUNT(*) FROM ticket_events WHERE ticket_id = :id"),
                {"id": ticket_id},
            ).scalar_one()
        assert mid_transaction_count == 0
        database.commit()

    with engine.connect() as connection:
        final_count = connection.execute(
            text("SELECT COUNT(*) FROM ticket_events WHERE ticket_id = :id"), {"id": ticket_id}
        ).scalar_one()
    assert final_count == 1


# ---------------------------------------------------------------------------
# Row 9: the DB-level SLA-cycle unique guard rejects a duplicate write with
# IntegrityError, and the connection recovers cleanly after rollback.
# ---------------------------------------------------------------------------


def test_duplicate_sla_cycle_event_is_rejected_by_the_unique_guard():
    engine = _engine()
    requester = 80901
    _seed_user(engine, user_id=requester, email="requester-audit9@test.local", role_code="USER")
    ticket_id = 80010
    _seed_ticket(engine, ticket_id=ticket_id, requester_id=requester, assignee_id=None)

    _append_event(
        engine,
        ticket_id=ticket_id,
        event_type=EventType.SLA_CYCLE_STARTED.value,
        scope=EventScope.USER_VISIBLE.value,
        actor_id=None,
        cycle_no=1,
    )

    with Session(engine) as database:
        AuditRepository(database).append(
            ticket_id=ticket_id,
            event_type=EventType.SLA_CYCLE_STARTED.value,
            scope=EventScope.USER_VISIBLE.value,
            actor_id=None,
            cycle_no=1,
        )
        with pytest.raises(IntegrityError):
            database.commit()
        # A job re-run is expected to catch IntegrityError, roll back, and
        # treat the cycle as already recorded -- verify the session is
        # actually usable again afterwards rather than left poisoned.
        database.rollback()
        still_one = database.execute(
            text(
                "SELECT COUNT(*) FROM ticket_events "
                "WHERE ticket_id = :id AND event_type = 'SLA_CYCLE_STARTED'"
            ),
            {"id": ticket_id},
        ).scalar_one()
        assert still_one == 1

    # A genuinely new cycle (different cycle_no) must still succeed -- the
    # guard is scoped to (ticket_id, cycle_no, event_type), not a blanket
    # one-SLA-event-per-ticket rule.
    _append_event(
        engine,
        ticket_id=ticket_id,
        event_type=EventType.SLA_CYCLE_STARTED.value,
        scope=EventScope.USER_VISIBLE.value,
        actor_id=None,
        cycle_no=2,
    )
    with engine.connect() as connection:
        total = connection.execute(
            text(
                "SELECT COUNT(*) FROM ticket_events "
                "WHERE ticket_id = :id AND event_type = 'SLA_CYCLE_STARTED'"
            ),
            {"id": ticket_id},
        ).scalar_one()
    assert total == 2
