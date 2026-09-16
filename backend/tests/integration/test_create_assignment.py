"""C's half of C023: real-MySQL coverage for
``app.domains.workflow.ticket_creation.initialize_ticket_workflow``.

This intentionally does NOT go through HTTP/API-15 -- Member B owns that
endpoint and ``app.domains.tickets.*`` is still an empty stub at the time
this test was written (C023.01/.06 -- routing this through the real
endpoint is B's half of C023, once B's create-ticket transaction exists
and calls this function). What C can and should verify now is that the
function C is responsible for behaves correctly against a real database:
C023.02 (ASSIGNED-with-candidate / UNASSIGNED-with-none, never NEW),
C023.03 (exactly the two events this function owns get written, no more,
no fewer) and C023.05 (a mid-sequence failure rolls back everything --
the ticket row, ``last_assigned_at`` and every event together).

Run only against a disposable schema, same convention as
``test_member_a_mysql.py``:

    RUN_MYSQL_INTEGRATION=1 pytest tests/integration/test_create_assignment.py

Uses its own ``service_desk_member_c_test`` schema name rather than
member A's, so the two integration tests never share -- or corrupt -- each
other's fixture data; this schema-per-member convention is not yet agreed
with the team and should be reconciled once everyone has an integration
test (flagged here rather than silently assumed).
"""

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domains.workflow.state_machine import TicketStatus
from app.domains.workflow.ticket_creation import initialize_ticket_workflow

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MYSQL_INTEGRATION") != "1",
    reason="Requires a disposable local MySQL integration schema.",
)


def _reset(engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for table in ("ticket_events", "tickets", "user_skills", "users"):
            connection.execute(text(f"DELETE FROM {table}"))
        connection.execute(text("SET FOREIGN_KEY_CHECKS=1"))
        connection.execute(text("UPDATE assignment_control SET updated_at = updated_at"))


def _seed_users_and_ticket(engine, *, ticket_id: int, with_candidate: bool) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO users
                  (user_id,email,password_hash,display_name,role_code,is_available)
                VALUES (9001,'requester-c023@test.local','x','Requester','USER',NULL)
                """
            )
        )
        if with_candidate:
            connection.execute(
                text(
                    """
                    INSERT INTO users
                      (user_id,email,password_hash,display_name,role_code,is_available)
                    VALUES (9002,'tier1-c023@test.local','x','Tier One','ENGINEER_TIER1',1)
                    """
                )
            )
            connection.execute(
                text("INSERT INTO user_skills (user_id,category_code) VALUES (9002,'NETWORK')")
            )
        connection.execute(
            text(
                """
                INSERT INTO tickets
                  (ticket_id,requester_id,title,description,category_code,
                   priority_code,status_code,assignee_id)
                VALUES
                  (:ticket_id,9001,'Integration ticket','Seeded for C023',
                   'NETWORK','MEDIUM','NEW',NULL)
                """
            ),
            {"ticket_id": ticket_id},
        )


def _fetch_ticket(engine, ticket_id: int):
    with engine.connect() as connection:
        return (
            connection.execute(
                text(
                    "SELECT status_code, assignee_id, sla_cycle_no, sla_deadline "
                    "FROM tickets WHERE ticket_id = :ticket_id"
                ),
                {"ticket_id": ticket_id},
            )
            .mappings()
            .one_or_none()
        )


def _fetch_events(engine, ticket_id: int) -> list[str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT event_type FROM ticket_events "
                "WHERE ticket_id = :ticket_id ORDER BY event_id"
            ),
            {"ticket_id": ticket_id},
        ).all()
        return [row[0] for row in rows]


def _engine():
    settings = get_settings()
    assert settings.database_url.endswith("/service_desk_member_c_test")
    return create_engine(settings.database_url)


def test_initial_assignment_with_a_candidate_sets_assigned_and_writes_both_events():
    engine = _engine()
    _reset(engine)
    ticket_id = 70001
    _seed_users_and_ticket(engine, ticket_id=ticket_id, with_candidate=True)

    with Session(engine) as database:
        outcome = initialize_ticket_workflow(
            database, ticket_id=ticket_id, category_code="NETWORK", now=datetime.now(UTC)
        )
        database.commit()

    assert outcome.status is TicketStatus.ASSIGNED
    assert outcome.assignee_id == 9002
    assert outcome.sla_cycle_no == 1

    row = _fetch_ticket(engine, ticket_id)
    assert row["status_code"] == "ASSIGNED"
    assert row["assignee_id"] == 9002
    assert row["sla_deadline"] is not None
    assert _fetch_events(engine, ticket_id) == ["SLA_CYCLE_STARTED", "AUTO_ASSIGNED"]


def test_initial_assignment_with_no_candidate_sets_unassigned_and_writes_only_the_cycle_event():
    engine = _engine()
    _reset(engine)
    ticket_id = 70002
    _seed_users_and_ticket(engine, ticket_id=ticket_id, with_candidate=False)

    with Session(engine) as database:
        outcome = initialize_ticket_workflow(
            database, ticket_id=ticket_id, category_code="NETWORK", now=datetime.now(UTC)
        )
        database.commit()

    assert outcome.status is TicketStatus.UNASSIGNED
    assert outcome.assignee_id is None

    row = _fetch_ticket(engine, ticket_id)
    assert row["status_code"] == "UNASSIGNED"
    assert row["assignee_id"] is None
    assert _fetch_events(engine, ticket_id) == ["SLA_CYCLE_STARTED"]


def test_a_failure_after_assignment_rolls_back_the_whole_transaction():
    """C023.05: simulate B's transaction failing (e.g. their own later step
    raises) by never committing -- everything this function wrote,
    including the assignee's ``last_assigned_at``, must vanish together.
    """
    engine = _engine()
    _reset(engine)
    ticket_id = 70003
    _seed_users_and_ticket(engine, ticket_id=ticket_id, with_candidate=True)

    with Session(engine) as database:
        initialize_ticket_workflow(
            database, ticket_id=ticket_id, category_code="NETWORK", now=datetime.now(UTC)
        )
        database.rollback()

    row = _fetch_ticket(engine, ticket_id)
    assert row["status_code"] == "NEW"
    assert row["assignee_id"] is None
    assert row["sla_cycle_no"] == 1  # column default, never touched
    assert row["sla_deadline"] is None
    assert _fetch_events(engine, ticket_id) == []

    with engine.connect() as connection:
        last_assigned_at = connection.execute(
            text("SELECT last_assigned_at FROM users WHERE user_id = 9002")
        ).scalar_one()
    assert last_assigned_at is None
