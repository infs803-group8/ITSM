"""C037: real-MySQL coverage for app.domains.sla.monitor_job.SlaMonitorJob
-- overlap safety, single-ticket-failure isolation, and long-outage
backfill/rerun idempotency.

Run only against a disposable schema, same convention as
test_member_a_mysql.py and test_create_assignment.py:

    RUN_MYSQL_INTEGRATION=1 pytest tests/integration/test_sla_job_recovery.py

Reuses test_create_assignment.py's own service_desk_member_c_test schema
(both are C's integration tests) rather than member A's schema, per that
file's own schema-per-member convention note.

Scope actually covered here, against every unit test in this stack's own
disclosure that sqlalchemy/pytest/fastapi are all absent from the sandbox
this was written in (no network egress to install them either): NONE of
this file has been executed. It is written to the shape C037's own
checklist and "验证范围" describe (T-JOB-03/04/05), for Andy to run against
his own local MySQL once this stack is pulled somewhere with a database.

What is deliberately NOT attempted here, and left to Andy/the team:
- T-JOB-03's overlap scenario is exercised with two Python threads against
  two separate engines/Sessions, each racing SlaMonitorJob.run_once() at
  the real ticket-row lock -- a genuine two-Session race, but on a single
  test machine's single MySQL instance, not the "two independent ECS
  Tasks" shape C037.01 actually describes. It is the closest thing to
  that shape a single pytest run can exercise.
- C037.04's connection-loss/deadlock retry path (already unit-tested
  with fakes in tests/unit/sla/test_monitor_job.py) is not re-exercised
  here against a real dropped connection -- simulating an actual MySQL
  disconnect mid-transaction from a test is its own significant piece of
  infrastructure (e.g. a proxy that can be killed mid-query) that this
  task's time budget does not cover; flagged rather than silently
  skipped.
- C037.05's "long stretch of downtime, multiple deadlines missed" is
  covered functionally (a cycle whose sla_started_at is far enough in the
  past that both thresholds were already crossed before the first scan
  ever ran), but not literally by leaving a job down for days -- the
  clock is manipulated by seeding an old sla_started_at, not by an
  injectable `now` on a real run (main()/run_once() default to the real
  clock in production; only the unit tests inject a frozen one).
- Retry/timeout/batch-size *parameter values* are explicitly not tuned
  or claimed here -- C037.06 hands those to Member A and says any
  undetermined number should be marked pending a load test, not asserted
  as a throughput guarantee.
"""

import os
import threading
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domains.sla.monitor_job import SlaMonitorJob

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MYSQL_INTEGRATION") != "1",
    reason="Requires a disposable local MySQL integration schema.",
)


def _engine():
    settings = get_settings()
    assert settings.database_url.endswith("/service_desk_member_c_test")
    return create_engine(settings.database_url)


def _reset(engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for table in ("ticket_events", "tickets", "user_skills", "users"):
            connection.execute(text(f"DELETE FROM {table}"))
        connection.execute(text("SET FOREIGN_KEY_CHECKS=1"))


def _seed_engineer_and_requester(engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO users
                  (user_id,email,password_hash,display_name,role_code,is_available)
                VALUES
                  (9101,'requester-c037@test.local','x','Requester','USER',NULL),
                  (9102,'tier1-c037@test.local','x','Tier One','ENGINEER_TIER1',1)
                """
            )
        )


def _seed_in_progress_ticket(
    engine, *, ticket_id: int, sla_started_at: datetime, sla_status_code: str = "ON_TRACK"
) -> None:
    """A ticket already past creation/assignment -- IN_PROGRESS, with its
    Engineering SLA cycle running from ``sla_started_at`` for the
    standard 48h window (matching this schema's service_config seed row,
    not re-read here -- if that seed ever changes, so must this literal).
    """
    sla_deadline = sla_started_at + timedelta(hours=48)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO tickets
                  (ticket_id,requester_id,title,description,category_code,
                   priority_code,status_code,assignee_id,
                   sla_cycle_no,sla_status_code,sla_started_at,sla_deadline)
                VALUES
                  (:ticket_id,9101,'Integration ticket','Seeded for C037',
                   'NETWORK','MEDIUM','IN_PROGRESS',9102,
                   1,:sla_status_code,:sla_started_at,:sla_deadline)
                """
            ),
            {
                "ticket_id": ticket_id,
                "sla_status_code": sla_status_code,
                "sla_started_at": sla_started_at.astimezone(UTC).replace(tzinfo=None),
                "sla_deadline": sla_deadline.astimezone(UTC).replace(tzinfo=None),
            },
        )


def _fetch_sla_status(engine, ticket_id: int) -> str:
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT sla_status_code FROM tickets WHERE ticket_id = :ticket_id"),
            {"ticket_id": ticket_id},
        ).scalar_one()


def _fetch_event_types(engine, ticket_id: int) -> list[str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT event_type FROM ticket_events "
                "WHERE ticket_id = :ticket_id ORDER BY event_id"
            ),
            {"ticket_id": ticket_id},
        ).all()
        return [row[0] for row in rows]


def test_a_long_missed_scan_backfills_at_risk_then_overdue_and_a_rerun_adds_nothing():
    """T-JOB-05 / Q09: a cycle started 3 days ago (well past both the 80%
    and 100% marks) is discovered by the very first scan that ever looks
    at it -- both SLA_AT_RISK and SLA_OVERDUE must be written, in that
    order, and a second run_once() immediately after must add nothing
    (the DB-level uq_ticket_events_cycle_guard is the backstop; C035's
    own re-validation, which no longer sees ON_TRACK/AT_RISK once the
    ticket is OVERDUE, is what should actually prevent it from trying).
    """
    engine = _engine()
    _reset(engine)
    _seed_engineer_and_requester(engine)
    ticket_id = 80001
    _seed_in_progress_ticket(engine, ticket_id=ticket_id, sla_started_at=datetime.now(UTC) - timedelta(days=3))

    with Session(engine) as database:
        first_summary = SlaMonitorJob(database, session_factory=lambda: Session(engine)).run_once()
        database.commit()

    assert first_summary.threshold.processed == 1
    assert first_summary.threshold.failed == 0
    assert _fetch_sla_status(engine, ticket_id) == "OVERDUE"
    assert _fetch_event_types(engine, ticket_id) == ["SLA_AT_RISK", "SLA_OVERDUE"]

    with Session(engine) as database:
        second_summary = SlaMonitorJob(database, session_factory=lambda: Session(engine)).run_once()
        database.commit()

    assert second_summary.threshold.processed == 0
    assert second_summary.threshold.skipped == 1  # already OVERDUE -> re-validated out, not re-written
    assert _fetch_event_types(engine, ticket_id) == ["SLA_AT_RISK", "SLA_OVERDUE"]  # unchanged


def test_a_single_ticket_failure_does_not_stop_the_rest_of_the_batch():
    """T-JOB-04 / C037.02: one ticket in a two-ticket page raises; the
    other must still be processed, and the run's own failure count (the
    thing main() turns into a non-zero exit code) must reflect it rather
    than silently reporting success.
    """
    engine = _engine()
    _reset(engine)
    _seed_engineer_and_requester(engine)
    healthy_ticket_id = 80011
    broken_ticket_id = 80012
    now = datetime.now(UTC)
    _seed_in_progress_ticket(engine, ticket_id=healthy_ticket_id, sla_started_at=now - timedelta(hours=39))
    _seed_in_progress_ticket(engine, ticket_id=broken_ticket_id, sla_started_at=now - timedelta(hours=39))

    with Session(engine) as database:
        job = SlaMonitorJob(database, session_factory=lambda: Session(engine))
        real_evaluate = job.sla.evaluate_threshold_scan

        def evaluate_with_injected_failure(*, ticket_id, now):
            if ticket_id == broken_ticket_id:
                raise RuntimeError("simulated failure for T-JOB-04")
            return real_evaluate(ticket_id=ticket_id, now=now)

        job.sla.evaluate_threshold_scan = evaluate_with_injected_failure
        summary = job.run_once(now=now)
        database.commit()

    assert summary.threshold.processed == 1
    assert summary.threshold.failed == 1
    assert summary.total_failed == 1  # this is exactly what main() turns into exit code 1
    assert _fetch_sla_status(engine, healthy_ticket_id) == "AT_RISK"
    # The broken ticket's own transaction was rolled back by _run_one's
    # except-Exception branch -- its status must be untouched, not half-written.
    assert _fetch_sla_status(engine, broken_ticket_id) == "ON_TRACK"


def test_two_concurrent_monitor_runs_against_the_same_overdue_ticket_write_the_event_once():
    """T-JOB-03: two independent Sessions (simulating two independent
    monitor processes/ECS Tasks) both pick up the same overdue ticket in
    the same instant. The row lock (SELECT ... FOR UPDATE inside
    evaluate_threshold_scan) must serialise them, and re-validation must
    make the loser's turn a no-op rather than a duplicate write --
    the uq_ticket_events_cycle_guard unique key is the last-resort
    backstop if re-validation somehow didn't catch it, so this test also
    incidentally proves that constraint is never actually needed on the
    happy path.
    """
    engine = _engine()
    _reset(engine)
    _seed_engineer_and_requester(engine)
    ticket_id = 80021
    _seed_in_progress_ticket(engine, ticket_id=ticket_id, sla_started_at=datetime.now(UTC) - timedelta(hours=49))

    results: dict[str, object] = {}
    barrier = threading.Barrier(2)

    def run_job(name: str) -> None:
        # Each thread gets its own independent Session/connection -- the
        # actual point under test is MySQL's row lock, not anything
        # Python-level.
        with Session(engine) as database:
            barrier.wait()  # start both threads' first statement as close together as possible
            summary = SlaMonitorJob(database, session_factory=lambda: Session(engine)).run_once()
            database.commit()
            results[name] = summary

    threads = [threading.Thread(target=run_job, name=n) for n in ("first", "second")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    processed_counts = [results[name].threshold.processed for name in ("first", "second")]
    skipped_counts = [results[name].threshold.skipped for name in ("first", "second")]
    assert sorted(processed_counts) == [0, 1]  # exactly one of the two actually wrote the event
    assert sorted(skipped_counts) == [0, 1]
    assert any(results[name].threshold.failed for name in ("first", "second")) is False
    assert _fetch_sla_status(engine, ticket_id) == "OVERDUE"
    assert _fetch_event_types(engine, ticket_id) == ["SLA_OVERDUE"]  # never duplicated


def test_pending_user_and_auto_close_candidates_are_picked_up_end_to_end():
    """A minimal real-MySQL smoke test for the two non-Engineering-SLA
    candidate families C036 added (unit-tested only against fakes in
    test_monitor_job.py) -- confirms the actual SQL in
    get_pending_user_timeout_candidates/get_auto_close_candidates and the
    idx_tickets_pending_user_job/idx_tickets_auto_close_job indexes they
    rely on are wired correctly end to end, not just shaped correctly.
    """
    engine = _engine()
    _reset(engine)
    _seed_engineer_and_requester(engine)
    now = datetime.now(UTC)
    pending_user_ticket_id = 80031
    resolved_ticket_id = 80032

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO tickets
                  (ticket_id,requester_id,title,description,category_code,priority_code,
                   status_code,assignee_id,sla_cycle_no,sla_status_code,
                   pending_user_reason,pending_user_deadline)
                VALUES
                  (:ticket_id,9101,'Pending user ticket','Seeded for C037','NETWORK','MEDIUM',
                   'PENDING_USER',9102,1,'PAUSED',
                   'INFORMATION_REQUIRED',:deadline)
                """
            ),
            {"ticket_id": pending_user_ticket_id, "deadline": (now - timedelta(hours=1)).replace(tzinfo=None)},
        )
        connection.execute(
            text(
                """
                INSERT INTO tickets
                  (ticket_id,requester_id,title,description,category_code,priority_code,
                   status_code,assignee_id,sla_cycle_no,sla_status_code,
                   resolution_summary,resolution_type,resolved_at,auto_close_at,
                   last_resolved_assignee_id)
                VALUES
                  (:ticket_id,9101,'Resolved ticket','Seeded for C037','NETWORK','MEDIUM',
                   'RESOLVED',9102,1,'MET',
                   'Fixed the router.','ENGINEER_RESOLVED',:resolved_at,:auto_close_at,9102)
                """
            ),
            {
                "ticket_id": resolved_ticket_id,
                "resolved_at": (now - timedelta(days=8)).replace(tzinfo=None),
                "auto_close_at": (now - timedelta(hours=1)).replace(tzinfo=None),
            },
        )

    with Session(engine) as database:
        summary = SlaMonitorJob(database, session_factory=lambda: Session(engine)).run_once(now=now)
        database.commit()

    assert summary.pending_user.processed == 1
    assert summary.auto_close.processed == 1

    with engine.connect() as connection:
        pending_user_status = connection.execute(
            text("SELECT status_code FROM tickets WHERE ticket_id = :ticket_id"),
            {"ticket_id": pending_user_ticket_id},
        ).scalar_one()
        resolved_status = connection.execute(
            text("SELECT status_code FROM tickets WHERE ticket_id = :ticket_id"),
            {"ticket_id": resolved_ticket_id},
        ).scalar_one()
    assert pending_user_status == "RESOLVED"  # auto-resolved by the 120h User Timer
    assert resolved_status == "CLOSED"  # auto-closed by the 7-day window
