"""Lazy + job-shared deadline enforcement (tasks C018, C019).

Baseline §4.7's "统一顺序" (lock -> re-validate -> update -> append event
-> commit) is owned by the caller (an API handler for the lazy path, or
the standalone SLA/deadline monitor job for the scheduled path); this
module is the one place that DECIDES what an expired deadline means and
does the actual field/event writes, so both callers can never disagree
about it (baseline §4.2's "API-24/API-29 与 SLA Job 复用同一 Deadline
Enforcement").

Neither method here reads the clock -- callers always supply ``now`` --
and neither commits. Both are idempotent by construction: they only
accept a snapshot that a repository method already confirmed is in the
right starting state (PENDING_USER for auto-resolve, RESOLVED for
auto-close), so a second call against an already-resolved/closed ticket
simply has no snapshot to work from (C018.06/C019.03).
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.enums import EventScope, EventType
from app.core.errors import ApplicationError
from app.domains.audit.service import AuditService
from app.domains.sla.cycle import auto_close_deadline
from app.domains.workflow.repository import WorkflowRepository
from app.domains.workflow.state_machine import PendingUserReason, ResolutionType


@dataclass(frozen=True)
class PendingUserSnapshot:
    ticket_id: int
    pending_user_reason: PendingUserReason
    pending_user_deadline: datetime
    resolution_summary: str | None
    assignee_id: int | None

    @classmethod
    def from_row(cls, row) -> "PendingUserSnapshot":
        return cls(
            ticket_id=int(row["ticket_id"]),
            pending_user_reason=PendingUserReason(str(row["pending_user_reason"])),
            pending_user_deadline=row["pending_user_deadline"],
            resolution_summary=row["resolution_summary"],
            assignee_id=int(row["assignee_id"]) if row["assignee_id"] is not None else None,
        )


@dataclass(frozen=True)
class ResolvedSnapshot:
    ticket_id: int
    auto_close_at: datetime

    @classmethod
    def from_row(cls, row) -> "ResolvedSnapshot":
        return cls(ticket_id=int(row["ticket_id"]), auto_close_at=row["auto_close_at"])


@dataclass(frozen=True)
class AutoResolveOutcome:
    applied: bool
    resolution_type: ResolutionType | None = None
    resolved_at: datetime | None = None
    auto_close_at: datetime | None = None


@dataclass(frozen=True)
class AutoCloseOutcome:
    applied: bool
    closed_at: datetime | None = None


#: User-visible system explanation for AUTO_NO_USER_RESPONSE. Never
#: invents an engineer's resolution -- C018.02.
_NO_RESPONSE_SUMMARY = (
    "This ticket was automatically resolved because no additional "
    "information was received from the requester within the response window."
)


class DeadlineService:
    def __init__(self, database: Session) -> None:
        self.database = database
        self.repository = WorkflowRepository(database)
        self.audit = AuditService(database)

    def check_pending_user_timeout(
        self,
        snapshot: PendingUserSnapshot,
        *,
        now: datetime,
        resolved_window_hours: int,
    ) -> AutoResolveOutcome:
        """C018.01-05. Returns ``applied=False`` (no write at all) when
        ``now`` is still before the deadline -- baseline §4.2's uniform
        "now < deadline allows user action, now >= deadline triggers the
        automatic outcome" boundary.
        """
        if now < snapshot.pending_user_deadline:
            return AutoResolveOutcome(applied=False)

        if snapshot.pending_user_reason == PendingUserReason.INFORMATION_REQUIRED:
            resolution_type = ResolutionType.AUTO_NO_USER_RESPONSE
            event_type = EventType.AUTO_RESOLVED_NO_USER_RESPONSE
            summary = _NO_RESPONSE_SUMMARY
        else:
            resolution_type = ResolutionType.AUTO_CONFIRMATION_TIMEOUT
            event_type = EventType.RESOLUTION_CONFIRMATION_TIMEOUT
            # Keep the engineer's own resolution_summary -- C018.03.
            summary = snapshot.resolution_summary

        resolved_at = now
        close_at = auto_close_deadline(
            resolved_at=resolved_at, resolved_window_hours=resolved_window_hours
        )

        self.repository.apply_auto_resolution(
            ticket_id=snapshot.ticket_id,
            resolution_type=resolution_type,
            resolution_summary=summary,
            resolved_at=resolved_at,
            auto_close_at=close_at,
            last_resolved_assignee_id=snapshot.assignee_id,
        )
        self.audit.append_event(
            ticket_id=snapshot.ticket_id,
            event_type=event_type,
            scope=EventScope.USER_VISIBLE,
            actor_id=None,
            metadata={"auto_close_at": close_at.isoformat()},
        )
        return AutoResolveOutcome(
            applied=True,
            resolution_type=resolution_type,
            resolved_at=resolved_at,
            auto_close_at=close_at,
        )

    def check_resolved_auto_close_timeout(
        self,
        snapshot: ResolvedSnapshot,
        *,
        now: datetime,
    ) -> AutoCloseOutcome:
        """C019.01-03. Same now-vs-deadline boundary as above, against
        ``auto_close_at`` instead of ``pending_user_deadline``. Does not
        start a new SLA cycle and does not touch resolution_*/resolved_at
        (C019.02) -- only status_code/closure_type/closed_at change.
        """
        if now < snapshot.auto_close_at:
            return AutoCloseOutcome(applied=False)

        closed_at = now
        self.repository.apply_auto_close(ticket_id=snapshot.ticket_id, closed_at=closed_at)
        self.audit.append_event(
            ticket_id=snapshot.ticket_id,
            event_type=EventType.TICKET_CLOSED_AUTO,
            scope=EventScope.USER_VISIBLE,
            actor_id=None,
        )
        return AutoCloseOutcome(applied=True, closed_at=closed_at)

    # ------------------------------------------------------------------
    # C020: the "auto outcome already committed, now return a conflict"
    # boundary. baseline §4.6: "API-24/API-29 在 120h 边界先执行 Auto
    # Resolve，再返回 409 USER_RESPONSE_WINDOW_EXPIRED；API-30/API-31 在
    # 7d 边界先执行 Auto Close，再返回 TICKET_CLOSED". These commit the
    # auto outcome THEMSELVES (independent of whatever the caller's own
    # transaction was about to do), then raise -- so a later rollback by
    # the caller's exception handler can never undo a result this method
    # has already reported as committed (C020.04).
    # ------------------------------------------------------------------

    def enforce_pending_user_not_expired(
        self,
        snapshot: PendingUserSnapshot,
        *,
        now: datetime,
        resolved_window_hours: int,
    ) -> None:
        """Guard for any write action that requires an still-open
        PENDING_USER window (API-24 Resume/Issue-Persists, API-29
        Confirm). Returns normally when the window is still open;
        otherwise commits the auto-resolve outcome and raises.
        """
        outcome = self.check_pending_user_timeout(
            snapshot, now=now, resolved_window_hours=resolved_window_hours
        )
        if not outcome.applied:
            return
        self.database.commit()
        raise ApplicationError(
            "USER_RESPONSE_WINDOW_EXPIRED",
            "The user response window has expired; the ticket was automatically resolved.",
            409,
        )

    def enforce_resolved_not_auto_closed(
        self, snapshot: ResolvedSnapshot, *, now: datetime
    ) -> None:
        """Guard for API-30 Reopen / API-31 Manual Close. Returns normally
        when the 7-day window is still open; otherwise commits the
        auto-close outcome and raises.
        """
        outcome = self.check_resolved_auto_close_timeout(snapshot, now=now)
        if not outcome.applied:
            return
        self.database.commit()
        raise ApplicationError(
            "TICKET_CLOSED",
            "This ticket was automatically closed; it accepts no further actions.",
            409,
        )
