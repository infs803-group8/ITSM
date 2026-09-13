"""Raw-SQL reads/writes for initial auto-assignment (C022).

Same raw-SQL-against-the-physical-table pattern as every other C repository
(app.domains.dashboard.repository, app.domains.audit.repository,
app.domains.sla.repository, app.domains.workflow.repository), since Member
B's User/Ticket ORM models don't exist yet.
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.clock import as_mysql_utc


class AssignmentRepository:
    def __init__(self, database: Session) -> None:
        self.database = database

    def lock_assignment_control(self) -> None:
        """C022.04: take the singleton lock before reading candidates or
        writing ``last_assigned_at``, so two concurrent ticket-creation
        transactions can never both pick the same lowest-load engineer.
        No external call may happen while this lock is held (C022.04) --
        the caller (``AssignmentService.assign_new_ticket``) does all of
        its work in the same database transaction and the ticket-creation
        flow that calls it (C023) is expected to commit promptly.
        """
        self.database.execute(
            text("SELECT control_id FROM assignment_control WHERE control_id = 1 FOR UPDATE")
        )

    def list_candidate_engineers(self, category_code: str) -> list[Mapping[str, Any]]:
        """C022.01: only ACTIVE, ``is_available = 1``, Tier 1 engineers whose
        skills include this ticket's category -- never Tier 2 or Vendor.
        C022.02: ``active_load`` counts only tickets currently ``ASSIGNED``,
        ``IN_PROGRESS``, ``PENDING_VENDOR`` or ``REOPENED`` and assigned to
        that engineer.
        """
        rows = (
            self.database.execute(
                text(
                    """
                    SELECT u.user_id, u.last_assigned_at,
                           COALESCE(loads.active_load, 0) AS active_load
                    FROM users u
                    JOIN user_skills s
                      ON s.user_id = u.user_id AND s.category_code = :category_code
                    LEFT JOIN (
                        SELECT assignee_id, COUNT(*) AS active_load FROM tickets
                        WHERE status_code IN
                              ('ASSIGNED', 'IN_PROGRESS', 'PENDING_VENDOR', 'REOPENED')
                        GROUP BY assignee_id
                    ) loads ON loads.assignee_id = u.user_id
                    WHERE u.role_code = 'ENGINEER_TIER1'
                      AND u.is_active = 1
                      AND u.is_available = 1
                    """
                ),
                {"category_code": category_code},
            )
            .mappings()
            .all()
        )
        return list(rows)

    def mark_last_assigned(self, *, user_id: int, when: datetime) -> None:
        """Part of the same locked transaction as the candidate read
        (C022.04) -- this is what makes the next concurrent creation see a
        different, updated ``last_assigned_at`` for this engineer rather
        than racing on stale data.
        """
        self.database.execute(
            text("UPDATE users SET last_assigned_at = :when WHERE user_id = :user_id"),
            {"when": as_mysql_utc(when), "user_id": user_id},
        )
