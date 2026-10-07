"""SLA cycle lifecycle: create, resume, pause, end (task C017).

The pure duration/deadline math lives in ``sla/cycle.py`` so it can be
unit-tested with no database at all; this module is the thin layer that
turns that math into a ``tickets`` row update plus an audit event, inside
the caller's own transaction. Per baseline §4.7, every write path
(workflow actions, the SLA monitor job) re-reads and re-validates before
writing -- this service does not lock or re-validate anything itself; the
caller is expected to already hold the row lock (``SELECT ... FOR
UPDATE``) before calling any of these methods.

Never commits. Historical cycles are never overwritten: each call issues
one more (append-only) TicketEvent via ``AuditService.append_event``
before/alongside updating the current-state columns on ``tickets``, so
the old SLA_OVERDUE/SLA_MET events for prior cycles remain queryable even
after the current cycle moves on (baseline §4.2's "historical cycles are appended to
TicketEvent; a new cycle never overwrites history").
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.clock import as_utc
from app.core.enums import EventScope, EventType
from app.domains.audit.service import AuditService
from app.domains.sla.cycle import (
    CycleWindow,
    SlaConfig,
    auto_close_deadline,
    first_cycle,
    next_cycle,
    start_cycle,
    user_response_deadline,
)
from app.domains.sla.repository import SlaRepository

_ON_TRACK = "ON_TRACK"
_PAUSED = "PAUSED"
_MET = "MET"
_OVERDUE = "OVERDUE"
_AT_RISK = "AT_RISK"

# C035.01: only these five statuses keep accruing Engineering SLA time.
# PENDING_USER's clock is paused (its own independent 120h User Timer,
# not this one); RESOLVED/CLOSED tickets have no Engineering cycle left
# to threaten. NEW is pre-creation-transaction and never observable here.
_ACTIVE_ENGINEERING_STATUSES = frozenset(
    {"UNASSIGNED", "ASSIGNED", "IN_PROGRESS", "PENDING_VENDOR", "REOPENED"}
)

# A ticket is only a genuine threshold-scan candidate while its cycle is
# still open (ON_TRACK) or has already been flagged AT_RISK but not yet
# OVERDUE. PAUSED/MET/OVERDUE all mean this cycle's outcome is already
# fixed -- re-scanning it must be a no-op (C035.06).
_SCAN_ELIGIBLE_SLA_STATUSES = frozenset({_ON_TRACK, _AT_RISK})


@dataclass(frozen=True)
class ThresholdScanOutcome:
    """C035's result for one ticket, one scan pass.

    ``new_sla_status`` is ``None`` when re-validation found nothing to do
    (no longer a candidate, or neither threshold has actually been
    crossed yet as of ``now``) -- the caller (eventually C036's job)
    should count that as a skip, not a failure. ``backfilled_at_risk`` is
    only ever ``True`` alongside ``new_sla_status == "OVERDUE"``: Q09's
    late-scan case, where the job's own delay let a cycle jump straight
    from ON_TRACK past both thresholds without an intervening run ever
    observing AT_RISK.
    """

    ticket_id: int
    cycle_no: int
    new_sla_status: str | None
    backfilled_at_risk: bool


class SlaCycleService:
    def __init__(self, database: Session) -> None:
        self.database = database
        self.repository = SlaRepository(database)
        self.audit = AuditService(database)

    def load_config(self) -> SlaConfig:
        return self.repository.get_config()

    def start_first_cycle(
        self,
        *,
        ticket_id: int,
        actor_id: int | None,
        now: datetime,
        config: SlaConfig,
    ) -> CycleWindow:
        """Initial assignment: cycle_no = 1."""
        window = first_cycle(started_at=now, config=config)
        self._apply_new_cycle(ticket_id=ticket_id, actor_id=actor_id, window=window)
        return window

    def start_new_cycle(
        self,
        *,
        ticket_id: int,
        previous_cycle_no: int,
        actor_id: int | None,
        now: datetime,
        config: SlaConfig,
    ) -> CycleWindow:
        """Resume, Issue Persists, or Reopen: cycle_no + 1, fresh 48h window.

        Escalation, Manager reassignment and Vendor request/response do
        NOT call this -- they keep the current cycle (baseline §4.2).
        """
        window = next_cycle(previous_cycle_no=previous_cycle_no, started_at=now, config=config)
        self._apply_new_cycle(ticket_id=ticket_id, actor_id=actor_id, window=window)
        return window

    def _apply_new_cycle(
        self, *, ticket_id: int, actor_id: int | None, window: CycleWindow
    ) -> None:
        self.repository.apply_cycle_window(ticket_id, window, sla_status=_ON_TRACK)
        self.audit.append_event(
            ticket_id=ticket_id,
            event_type=EventType.SLA_CYCLE_STARTED,
            scope=EventScope.USER_VISIBLE,
            actor_id=actor_id,
            cycle_no=window.cycle_no,
            metadata={"deadline": window.deadline.isoformat()},
        )

    def compute_user_response_deadline(self, *, now: datetime) -> datetime:
        """The independent 120h User Timer deadline (C026.03), read from
        ``service_config`` fresh every call rather than threaded through
        ``SlaConfig`` -- see ``SlaRepository.get_user_response_hours``'s
        own docstring for why.
        """
        hours = self.repository.get_user_response_hours()
        return user_response_deadline(started_at=now, user_response_hours=hours)

    def compute_auto_close_deadline(self, *, resolved_at: datetime) -> datetime:
        """The 7-day (168h) RESOLVED -> auto_close_at deadline (C032's
        Confirm Resolution), read from ``service_config`` fresh every
        call -- same rationale as ``compute_user_response_deadline``.
        """
        hours = self.repository.get_resolved_window_hours()
        return auto_close_deadline(resolved_at=resolved_at, resolved_window_hours=hours)

    def pause_current_cycle(self, *, ticket_id: int, cycle_no: int, actor_id: int | None) -> None:
        """Request User Info: the current cycle ends as PAUSED; no new cycle
        starts until Resume/Issue Persists (baseline §4.2).
        """
        self.repository.mark_sla_status(ticket_id, _PAUSED)
        self.audit.append_event(
            ticket_id=ticket_id,
            event_type=EventType.SLA_PAUSED,
            scope=EventScope.USER_VISIBLE,
            actor_id=actor_id,
            cycle_no=cycle_no,
        )

    def mark_met(self, *, ticket_id: int, cycle_no: int, actor_id: int | None) -> None:
        """Submit Resolution before the deadline: fix the cycle outcome as MET."""
        self.repository.mark_sla_status(ticket_id, _MET)
        self.audit.append_event(
            ticket_id=ticket_id,
            event_type=EventType.SLA_MET,
            scope=EventScope.USER_VISIBLE,
            actor_id=actor_id,
            cycle_no=cycle_no,
        )

    def mark_overdue(self, *, ticket_id: int, cycle_no: int) -> None:
        """SLA monitor / lazy deadline check: fix the cycle outcome as OVERDUE.

        System-generated (``actor_id=None``); the
        ``uq_ticket_events_cycle_guard`` unique key on
        ``(ticket_id, cycle_no, event_type)`` makes a repeated job run for
        the same cycle a no-op at the database level rather than this
        service's responsibility to de-duplicate.
        """
        self.repository.mark_sla_status(ticket_id, _OVERDUE)
        self.audit.append_event(
            ticket_id=ticket_id,
            event_type=EventType.SLA_OVERDUE,
            scope=EventScope.USER_VISIBLE,
            actor_id=None,
            cycle_no=cycle_no,
        )

    def mark_at_risk(self, *, ticket_id: int, cycle_no: int) -> None:
        """SLA monitor: 80% threshold crossed, still before the deadline."""
        self.repository.mark_sla_status(ticket_id, _AT_RISK)
        self.audit.append_event(
            ticket_id=ticket_id,
            event_type=EventType.SLA_AT_RISK,
            scope=EventScope.USER_VISIBLE,
            actor_id=None,
            cycle_no=cycle_no,
        )

    def evaluate_threshold_scan(
        self, *, ticket_id: int, now: datetime
    ) -> ThresholdScanOutcome | None:
        """C035: re-lock, re-validate, and (if warranted) write the AT_RISK
        and/or OVERDUE crossing for one ticket -- one candidate out of
        C036's future bounded batch.

        Deliberately takes only ``ticket_id``, never a cached status/cycle
        snapshot from whatever produced the candidate list: this method's
        own ``SELECT ... FOR UPDATE`` is the only source of truth it
        trusts, so a candidate that a concurrent workflow action already
        moved into PENDING_USER/RESOLVED/CLOSED, paused, resolved, or
        pushed into a new cycle since the batch was built is re-read here
        as it stands right now and safely turns into a no-op
        (``new_sla_status=None``) rather than clobbering a newer cycle
        with a stale one (C035.05).

        Returns ``None`` if the ticket does not exist, is not currently in
        one of the five active-Engineering-SLA statuses, its
        ``sla_status_code`` is not ON_TRACK/AT_RISK (already OVERDUE, or
        the cycle ended via PAUSED/MET), or -- even after all of the
        above -- ``now`` has not actually reached either threshold yet.
        Every write this method does make is idempotent across re-runs
        for the *same* cycle: the DB-level
        ``uq_ticket_events_cycle_guard`` unique key is the final backstop,
        but in the ordinary (non-crash) case re-validation above already
        prevents a second write, since a ticket already marked AT_RISK or
        OVERDUE for this cycle no longer satisfies
        ``_SCAN_ELIGIBLE_SLA_STATUSES``/the deadline comparison below.

        Never fabricates a backdated ``occurred_at`` for a late-discovered
        threshold (Q09, C035.04): both ``mark_at_risk`` and
        ``mark_overdue`` let ``ticket_events.occurred_at`` fall through to
        its own ``CURRENT_TIMESTAMP(6)`` column default, i.e. the moment
        this scan actually runs -- never the moment the threshold would
        have first been crossed had a scan run on time.
        """
        row = self.repository.get_cycle_state(ticket_id, for_update=True)
        if row is None:
            return None
        if row["status_code"] not in _ACTIVE_ENGINEERING_STATUSES:
            return None
        if row["sla_status_code"] not in _SCAN_ELIGIBLE_SLA_STATUSES:
            return None

        config = self.repository.get_config()
        window = start_cycle(
            cycle_no=int(row["sla_cycle_no"]),
            started_at=as_utc(row["sla_started_at"]),
            config=config,
        )

        if now >= window.deadline:
            # C035.02: use >=, keep the more severe state. A cycle that
            # was still ON_TRACK the last time anything looked at it (job
            # skipped a run, or this is the very first scan after the
            # deadline already passed) crossed both thresholds with
            # nothing in between ever observing AT_RISK -- Q09 says
            # backfill that AT_RISK event rather than silently jumping
            # straight to OVERDUE, so the history stays complete.
            backfilled_at_risk = row["sla_status_code"] == _ON_TRACK
            if backfilled_at_risk:
                self.mark_at_risk(ticket_id=ticket_id, cycle_no=int(row["sla_cycle_no"]))
            self.mark_overdue(ticket_id=ticket_id, cycle_no=int(row["sla_cycle_no"]))
            return ThresholdScanOutcome(
                ticket_id=ticket_id,
                cycle_no=int(row["sla_cycle_no"]),
                new_sla_status=_OVERDUE,
                backfilled_at_risk=backfilled_at_risk,
            )

        if now >= window.at_risk_at and row["sla_status_code"] == _ON_TRACK:
            self.mark_at_risk(ticket_id=ticket_id, cycle_no=int(row["sla_cycle_no"]))
            return ThresholdScanOutcome(
                ticket_id=ticket_id,
                cycle_no=int(row["sla_cycle_no"]),
                new_sla_status=_AT_RISK,
                backfilled_at_risk=False,
            )

        return None
