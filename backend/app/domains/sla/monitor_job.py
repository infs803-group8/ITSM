"""Standalone SLA/deadline monitor entrypoint (C036).

One module, one exit: ``run_once()`` scans every candidate exactly once
across the three deadline families C already owns a shared, lock-and-
revalidate service for -- Engineering SLA thresholds (C035), the 120h
User Timer (C018), and the 7-day auto-close window (C019) -- and returns.
There is no internal scheduling loop here; per C036.01, the recurring
cadence belongs to whatever invokes this module (an ECS scheduled Task,
a cron entry, a local `python -m app.domains.sla.monitor_job` call), not
to this process itself or to Uvicorn startup.

Mirrors ``app.domains.attachments.cleanup_job`` exactly in shape: one
shared ``Session`` for the whole run, a keyset-paginated (never OFFSET)
candidate cursor per category so a page already handled is never
re-offered and a row that changes between pages is never silently
skipped, and one commit/rollback per ticket rather than one long
transaction over an entire batch (C036.03) -- this job never holds a
row's lock past that single ticket's own write.

Each candidate is independently re-validated under its own
``SELECT ... FOR UPDATE`` by the very same service method C's HTTP write
paths and unit tests already exercise (``SlaCycleService.
evaluate_threshold_scan``, ``DeadlineService.check_pending_user_timeout``,
``DeadlineService.check_resolved_auto_close_timeout``) -- this module
adds no new business logic of its own, only the batch-scan wiring around
those three.

No dry-run mode is implemented (C036.04 makes it optional -- "if dry-run
mode is added" -- and it is skipped here to keep this task's scope to what the
checklist requires); ``run_once`` and its exit code are what C036.04
actually requires, and both exist below.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.clock import utc_now
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.domains.sla.service import SlaCycleService
from app.domains.workflow.deadline_service import (
    DeadlineService,
    PendingUserSnapshot,
    ResolvedSnapshot,
)
from app.domains.workflow.repository import WorkflowRepository

logger = logging.getLogger(__name__)

#: Database page size per category, per keyset page. Not a throughput
#: target (C037.06 explicitly reserves that for a future load test) --
#: just a bound on how much one round trip re-reads.
_DEFAULT_PAGE_SIZE = 200

#: C037.04: bounded retries for a connection-class failure only (server
#: gone away, deadlock) -- so up to 3 total attempts per ticket. A
#: placeholder value, not a load-tested constant: C037.06 explicitly
#: hands the real retry/timeout/batch parameters to Member A and says
#: not to claim a throughput number without a load test, so this number
#: exists only to keep a genuinely wedged connection from retrying
#: forever, not as a tuned production setting.
_MAX_CONNECTION_RETRIES = 2


@dataclass
class CategoryCounts:
    """C036.05's per-category processed/skipped/failed counters.

    ``skipped`` covers a candidate that the SQL query believed was due
    but re-validation under lock found was not actually eligible anymore
    (a concurrent workflow action already moved it on) or not yet past
    its own precise deadline -- either way, correctly not written to, not
    a failure.
    """

    processed: int = 0
    skipped: int = 0
    failed: int = 0


@dataclass
class RunSummary:
    """C036.04's testable ``run_once`` return value; C036.05's log line is
    built entirely from this (plus the release version, which this
    module does not itself depend on -- ``main()`` reads it separately).
    """

    run_id: str
    started_at: datetime
    finished_at: datetime
    threshold: CategoryCounts = field(default_factory=CategoryCounts)
    pending_user: CategoryCounts = field(default_factory=CategoryCounts)
    auto_close: CategoryCounts = field(default_factory=CategoryCounts)

    @property
    def total_processed(self) -> int:
        return self.threshold.processed + self.pending_user.processed + self.auto_close.processed

    @property
    def total_skipped(self) -> int:
        return self.threshold.skipped + self.pending_user.skipped + self.auto_close.skipped

    @property
    def total_failed(self) -> int:
        return self.threshold.failed + self.pending_user.failed + self.auto_close.failed


class SlaMonitorJob:
    def __init__(
        self,
        database: Session,
        *,
        session_factory: Callable[[], Session] | None = None,
    ) -> None:
        """``session_factory`` is optional and only used for C037.04's
        connection-loss/deadlock recovery: when it is supplied, a
        ``sqlalchemy.exc.OperationalError`` from ``process_one`` (the
        real error class MySQL connection loss and deadlocks both
        surface as through pymysql) discards this job's current
        ``Session`` entirely and opens a brand new one from the factory
        before a bounded number of retries -- never resuming on the
        broken Session, and never trusting anything it may have cached.
        Callers that don't need this recovery path (every unit test in
        this stack, which never raises OperationalError) can omit it.
        """
        self.database = database
        self._session_factory = session_factory
        self._rebuild_collaborators()

    def _rebuild_collaborators(self) -> None:
        self.workflow_repository = WorkflowRepository(self.database)
        self.sla = SlaCycleService(self.database)
        self.deadlines = DeadlineService(self.database)

    def _discard_session_and_reopen(self) -> None:
        """C037.04: never keep using a ``Session`` whose connection just
        broke or whose transaction just deadlocked. Best-effort close of
        the old one (it may already be unusable, hence the swallow), then
        a completely fresh ``Session`` and fresh repository/service
        instances built against it -- so a retried ``process_one`` call
        re-reads its candidate from scratch rather than trusting anything
        the dead Session's identity map may have cached.
        """
        try:
            self.database.close()
        except Exception:
            pass
        if self._session_factory is None:
            # No factory to rebuild from -- the caller opted out of this
            # recovery path. Roll back so at least the next statement on
            # this same Session doesn't inherit an aborted transaction.
            try:
                self.database.rollback()
            except Exception:
                pass
            return
        self.database = self._session_factory()
        self._rebuild_collaborators()

    def run_once(
        self, *, now: datetime | None = None, limit: int = _DEFAULT_PAGE_SIZE
    ) -> RunSummary:
        """C036.01/.04: one full pass over all three candidate families,
        then return -- never loops on a timer itself.

        ``now`` is injectable (C036.06's "frozen clock" requirement) so a test
        can freeze time and assert exact threshold-crossing behaviour;
        production callers (``main()`` below) leave it as the real clock.
        """
        started_at = now or utc_now()
        run_id = str(uuid4())

        threshold = self._scan_thresholds(now=started_at, limit=limit)
        pending_user = self._scan_pending_user_timeouts(now=started_at, limit=limit)
        auto_close = self._scan_auto_close(now=started_at, limit=limit)

        return RunSummary(
            run_id=run_id,
            started_at=started_at,
            finished_at=utc_now(),
            threshold=threshold,
            pending_user=pending_user,
            auto_close=auto_close,
        )

    # ------------------------------------------------------------------
    # Category scans -- each is: fetch one bounded/keyset page, process
    # every ticket in it one at a time (own commit/rollback), advance the
    # cursor to the last id seen, repeat until a page comes back empty.
    # ------------------------------------------------------------------

    def _scan_thresholds(self, *, now: datetime, limit: int) -> CategoryCounts:
        config = self.sla.load_config()
        at_risk_hours = config.engineering_sla_hours * config.at_risk_percent / 100
        at_risk_cutoff = now - timedelta(hours=at_risk_hours)

        def fetch(after_ticket_id: int) -> list[int]:
            return self.sla.repository.get_threshold_scan_candidates(
                now=now, at_risk_cutoff=at_risk_cutoff, limit=limit, after_ticket_id=after_ticket_id
            )

        def process(ticket_id: int) -> bool:
            outcome = self.sla.evaluate_threshold_scan(ticket_id=ticket_id, now=now)
            return outcome is not None

        return self._run_batch(fetch_candidates=fetch, process_one=process)

    def _scan_pending_user_timeouts(self, *, now: datetime, limit: int) -> CategoryCounts:
        resolved_window_hours = self.sla.repository.get_resolved_window_hours()

        def fetch(after_ticket_id: int) -> list[int]:
            return self.workflow_repository.get_pending_user_timeout_candidates(
                now=now, limit=limit, after_ticket_id=after_ticket_id
            )

        def process(ticket_id: int) -> bool:
            row = self.workflow_repository.get_pending_user_snapshot(ticket_id)
            if row is None:
                return False
            snapshot = PendingUserSnapshot.from_row(row)
            outcome = self.deadlines.check_pending_user_timeout(
                snapshot, now=now, resolved_window_hours=resolved_window_hours
            )
            return outcome.applied

        return self._run_batch(fetch_candidates=fetch, process_one=process)

    def _scan_auto_close(self, *, now: datetime, limit: int) -> CategoryCounts:
        def fetch(after_ticket_id: int) -> list[int]:
            return self.workflow_repository.get_auto_close_candidates(
                now=now, limit=limit, after_ticket_id=after_ticket_id
            )

        def process(ticket_id: int) -> bool:
            row = self.workflow_repository.get_resolved_snapshot(ticket_id)
            if row is None:
                return False
            snapshot = ResolvedSnapshot.from_row(row)
            outcome = self.deadlines.check_resolved_auto_close_timeout(snapshot, now=now)
            return outcome.applied

        return self._run_batch(fetch_candidates=fetch, process_one=process)

    def _run_batch(self, *, fetch_candidates, process_one) -> CategoryCounts:
        counts = CategoryCounts()
        after_ticket_id = 0
        while True:
            # Start each page on a clean transaction -- same precedent as
            # attachments/cleanup_job.py's own pre-page rollback.
            self.database.rollback()
            candidates = fetch_candidates(after_ticket_id)
            if not candidates:
                break
            for ticket_id in candidates:
                self._run_one(counts, ticket_id, process_one)
            after_ticket_id = candidates[-1]
        return counts

    def _run_one(self, counts: CategoryCounts, ticket_id: int, process_one) -> None:
        attempt = 1
        while True:
            try:
                processed = process_one(ticket_id)
            except OperationalError:
                # C037.04: connection loss ("MySQL server has gone away")
                # and a deadlock both surface through pymysql as
                # OperationalError -- the one class of failure worth a
                # bounded retry, and only after discarding the Session
                # that hit it (never continuing to issue statements on a
                # connection that may already be dead).
                self._discard_session_and_reopen()
                if self._session_factory is None or attempt > _MAX_CONNECTION_RETRIES:
                    counts.failed += 1
                    logger.warning(
                        "SLA monitor: ticket %s failed after %d attempt(s) (connection error)",
                        ticket_id,
                        attempt,
                    )
                    return
                logger.warning(
                    "SLA monitor: ticket %s hit a connection error, retrying (attempt %d)",
                    ticket_id,
                    attempt,
                )
                attempt += 1
                continue
            except Exception:
                # C036.05: never log the exception message itself (it
                # could echo back request/DB content) -- only that this
                # ticket failed, so an operator can go look at it
                # directly. Any non-connection-class failure is not
                # retried here -- it is a business-logic/data problem
                # that a retry would not fix -- so it is isolated from
                # every other candidate in the batch and counted, never
                # silently swallowed.
                self.database.rollback()
                counts.failed += 1
                logger.warning("SLA monitor: ticket %s failed during processing", ticket_id)
                return
            if processed:
                self.database.commit()
                counts.processed += 1
            else:
                self.database.rollback()
                counts.skipped += 1
            return


def main() -> int:
    """C036.01/.06: one scan, then exit -- no loop, no Uvicorn lifespan
    hook. Returns the process exit code C036.04/C037.02 requires: 0 only
    when every candidate this run touched was either processed or
    cleanly skipped, 1 if anything failed -- including a ticket that
    exhausted its C037.04 connection-loss retries -- never swallowed
    into a 0.
    """
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    with SessionLocal() as database:
        summary = SlaMonitorJob(database, session_factory=SessionLocal).run_once()
    logger.info(
        "SLA monitor run finished run_id=%s version=%s started_at=%s finished_at=%s "
        "threshold(processed=%d skipped=%d failed=%d) "
        "pending_user(processed=%d skipped=%d failed=%d) "
        "auto_close(processed=%d skipped=%d failed=%d)",
        summary.run_id,
        settings.release_version,
        summary.started_at.isoformat(),
        summary.finished_at.isoformat(),
        summary.threshold.processed,
        summary.threshold.skipped,
        summary.threshold.failed,
        summary.pending_user.processed,
        summary.pending_user.skipped,
        summary.pending_user.failed,
        summary.auto_close.processed,
        summary.auto_close.skipped,
        summary.auto_close.failed,
    )
    return 1 if summary.total_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
