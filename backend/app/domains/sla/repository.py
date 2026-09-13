"""Raw-SQL reads/writes for the SLA columns on ``tickets`` (task C017).

Uses the same raw-SQL-against-the-physical-table pattern as
``app.domains.dashboard.repository`` and ``app.domains.audit.repository``,
since Member B's Ticket ORM model does not exist yet. Only ever touches
the four SLA columns (``sla_cycle_no``, ``sla_status_code``,
``sla_started_at``, ``sla_deadline``) -- everything else on the row is
another domain's concern.
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.clock import as_mysql_utc
from app.domains.sla.cycle import CycleWindow, SlaConfig


class SlaRepository:
    def __init__(self, database: Session) -> None:
        self.database = database

    def get_config(self) -> SlaConfig:
        row = (
            self.database.execute(
                text(
                    "SELECT engineering_sla_hours, at_risk_percent "
                    "FROM service_config WHERE config_id = 1"
                )
            )
            .mappings()
            .one()
        )
        return SlaConfig(
            engineering_sla_hours=int(row["engineering_sla_hours"]),
            at_risk_percent=int(row["at_risk_percent"]),
        )

    def get_user_response_hours(self) -> int:
        """The independent 120h User Timer's configured length (C026.03's
        ``PENDING_USER``/``INFORMATION_REQUIRED`` deadline, and later
        C031's ``RESOLUTION_CONFIRMATION`` deadline).

        Deliberately its own single-column query rather than a field on
        ``SlaConfig`` -- ``SlaConfig`` is already constructed positionally
        by name in two C017 test files
        (``tests/unit/sla/test_service.py``, ``tests/unit/sla/test_cycle.py``)
        on an earlier, already-stacked branch; adding a required field
        there would silently break those without editing files this task
        has no other reason to touch.
        """
        row = (
            self.database.execute(
                text("SELECT user_response_hours FROM service_config WHERE config_id = 1")
            )
            .mappings()
            .one()
        )
        return int(row["user_response_hours"])

    def get_resolved_window_hours(self) -> int:
        """The 168h (7-day) RESOLVED->CLOSED auto-close window length
        (C027.02/.06's shared ``DeadlineService.enforce_pending_user_not_
        expired`` call needs it to compute the auto-resolve outcome's own
        ``auto_close_at`` when the 120h User Timer has already expired).

        Same single-column-query rationale as ``get_user_response_hours``.
        """
        row = (
            self.database.execute(
                text("SELECT resolved_window_hours FROM service_config WHERE config_id = 1")
            )
            .mappings()
            .one()
        )
        return int(row["resolved_window_hours"])

    def get_cycle_state(self, ticket_id: int, *, for_update: bool = False) -> Mapping[str, Any] | None:
        """Includes ``status_code`` alongside the four SLA columns -- C035's
        threshold scan needs it (only UNASSIGNED/ASSIGNED/IN_PROGRESS/
        PENDING_VENDOR/REOPENED tickets keep accruing Engineering SLA
        time) as well as the SLA-only callers this method already served
        before C035 existed.
        """
        lock = " FOR UPDATE" if for_update else ""
        return (
            self.database.execute(
                text(
                    "SELECT ticket_id, status_code, sla_cycle_no, sla_status_code, "
                    "sla_started_at, sla_deadline FROM tickets WHERE ticket_id = :ticket_id" + lock
                ),
                {"ticket_id": ticket_id},
            )
            .mappings()
            .one_or_none()
        )

    def apply_cycle_window(self, ticket_id: int, window: CycleWindow, *, sla_status: str) -> None:
        """Same-transaction UPDATE. schema.sql's chk_tickets_sla_times requires
        sla_started_at/sla_deadline to be set together with deadline > started,
        which a fresh CycleWindow always satisfies.
        """
        self.database.execute(
            text(
                """
                UPDATE tickets
                SET sla_cycle_no = :cycle_no,
                    sla_status_code = :sla_status,
                    sla_started_at = :started_at,
                    sla_deadline = :deadline
                WHERE ticket_id = :ticket_id
                """
            ),
            {
                "cycle_no": window.cycle_no,
                "sla_status": sla_status,
                "started_at": as_mysql_utc(window.started_at),
                "deadline": as_mysql_utc(window.deadline),
                "ticket_id": ticket_id,
            },
        )

    def mark_sla_status(self, ticket_id: int, sla_status: str) -> None:
        """Change only sla_status_code -- used for PAUSED/AT_RISK/OVERDUE/MET
        transitions that do not start a new cycle window.
        """
        self.database.execute(
            text("UPDATE tickets SET sla_status_code = :sla_status WHERE ticket_id = :ticket_id"),
            {"sla_status": sla_status, "ticket_id": ticket_id},
        )

    def get_threshold_scan_candidates(
        self,
        *,
        now: datetime,
        at_risk_cutoff: datetime,
        limit: int,
        after_ticket_id: int = 0,
    ) -> list[int]:
        """C036.02: bounded, keyset-paginated ticket ids whose Engineering
        SLA has crossed the 80% or 100% mark as of ``now``.

        ``at_risk_cutoff`` is ``now`` minus the config's 80%-of-cycle
        offset (computed by the caller, which already has ``SlaConfig`` in
        hand from ``get_config()`` -- this method stays a pure filter, no
        duration math of its own). A ticket qualifies either because its
        already-known ``sla_deadline`` (the 100% mark) has passed, or
        because it is still ON_TRACK and its cycle started early enough
        that 80% of the cycle has elapsed; a ticket already AT_RISK is
        only re-offered here on account of the deadline branch, since its
        80%-crossing was already handled by an earlier run.

        Keyset (``ticket_id > after_ticket_id``), not OFFSET: C036.02
        explicitly calls for pagination that stays stable while earlier
        rows change between pages, same rationale as
        ``attachments/cleanup_job.py``'s own cursor. Matches
        ``idx_tickets_sla_monitor`` (sla_status_code, sla_deadline,
        status_code, ticket_id).
        """
        rows = self.database.execute(
            text(
                """
                SELECT ticket_id
                FROM tickets
                WHERE ticket_id > :after_ticket_id
                  AND status_code IN
                    ('UNASSIGNED', 'ASSIGNED', 'IN_PROGRESS', 'PENDING_VENDOR', 'REOPENED')
                  AND sla_status_code IN ('ON_TRACK', 'AT_RISK')
                  AND (
                    sla_deadline <= :now
                    OR (sla_status_code = 'ON_TRACK' AND sla_started_at <= :at_risk_cutoff)
                  )
                ORDER BY ticket_id
                LIMIT :limit
                """
            ),
            {
                "after_ticket_id": after_ticket_id,
                "now": as_mysql_utc(now),
                "at_risk_cutoff": as_mysql_utc(at_risk_cutoff),
                "limit": limit,
            },
        ).all()
        return [int(row[0]) for row in rows]
