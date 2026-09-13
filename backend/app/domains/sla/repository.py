"""Raw-SQL reads/writes for the SLA columns on ``tickets`` (task C017).

Uses the same raw-SQL-against-the-physical-table pattern as
``app.domains.dashboard.repository`` and ``app.domains.audit.repository``,
since Member B's Ticket ORM model does not exist yet. Only ever touches
the four SLA columns (``sla_cycle_no``, ``sla_status_code``,
``sla_started_at``, ``sla_deadline``) -- everything else on the row is
another domain's concern.
"""

from collections.abc import Mapping
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

    def get_cycle_state(self, ticket_id: int, *, for_update: bool = False) -> Mapping[str, Any] | None:
        lock = " FOR UPDATE" if for_update else ""
        return (
            self.database.execute(
                text(
                    "SELECT ticket_id, sla_cycle_no, sla_status_code, sla_started_at, "
                    "sla_deadline FROM tickets WHERE ticket_id = :ticket_id" + lock
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
