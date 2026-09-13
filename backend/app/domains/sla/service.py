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
after the current cycle moves on (baseline §4.2's "历史 Cycle...只追加到
TicketEvent；新 Cycle 不覆盖历史").
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.enums import EventScope, EventType
from app.domains.audit.service import AuditService
from app.domains.sla.cycle import CycleWindow, SlaConfig, first_cycle, next_cycle
from app.domains.sla.repository import SlaRepository

_ON_TRACK = "ON_TRACK"
_PAUSED = "PAUSED"
_MET = "MET"
_OVERDUE = "OVERDUE"
_AT_RISK = "AT_RISK"


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

    def _apply_new_cycle(self, *, ticket_id: int, actor_id: int | None, window: CycleWindow) -> None:
        self.repository.apply_cycle_window(ticket_id, window, sla_status=_ON_TRACK)
        self.audit.append_event(
            ticket_id=ticket_id,
            event_type=EventType.SLA_CYCLE_STARTED,
            scope=EventScope.USER_VISIBLE,
            actor_id=actor_id,
            cycle_no=window.cycle_no,
            metadata={"deadline": window.deadline.isoformat()},
        )

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
