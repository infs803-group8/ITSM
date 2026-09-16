"""Raw-SQL reads/writes for the workflow columns on `tickets` (task C018+).

Same raw-SQL-against-the-physical-table pattern as
app.domains.dashboard.repository, app.domains.audit.repository and
app.domains.sla.repository, since Member B's Ticket ORM does not exist
yet. Scoped to the columns C's write-path services own: status_code,
assignee_id, pending_user_reason/deadline, resolution_*, closure_*,
last_resolved_assignee_id. Category/priority/title/description stay B's.
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.clock import as_mysql_utc
from app.domains.workflow.state_machine import ClosureType, ResolutionType


class WorkflowRepository:
    def __init__(self, database: Session) -> None:
        self.database = database

    def get_ticket_for_update(self, ticket_id: int) -> Mapping[str, Any] | None:
        """Baseline §4.7 step 1: SELECT ... FOR UPDATE before any workflow write."""
        return (
            self.database.execute(
                text(
                    """
                    SELECT ticket_id, status_code, assignee_id, requester_id,
                           sla_cycle_no, sla_status_code, pending_user_reason,
                           pending_user_deadline, resolution_summary, resolution_type,
                           auto_close_at
                    FROM tickets
                    WHERE ticket_id = :ticket_id
                    FOR UPDATE
                    """
                ),
                {"ticket_id": ticket_id},
            )
            .mappings()
            .one_or_none()
        )

    def get_pending_user_snapshot(self, ticket_id: int) -> Mapping[str, Any] | None:
        """None when the ticket isn't PENDING_USER -- callers use this to make
        auto-resolve idempotent (C018.06) without special-casing RESOLVED/CLOSED
        themselves: there is simply no snapshot to act on.
        """
        row = self.get_ticket_for_update(ticket_id)
        if row is None or row["status_code"] != "PENDING_USER":
            return None
        return row

    def apply_auto_resolution(
        self,
        *,
        ticket_id: int,
        resolution_type: ResolutionType,
        resolution_summary: str | None,
        resolved_at: datetime,
        auto_close_at: datetime,
        last_resolved_assignee_id: int | None,
    ) -> None:
        """C018.04: set RESOLVED and its resolution/closure-window fields,
        clear the pending_user_* fields (chk_tickets_pending_user requires
        both null once status leaves PENDING_USER).
        """
        self.database.execute(
            text(
                """
                UPDATE tickets
                SET status_code = 'RESOLVED',
                    pending_user_reason = NULL,
                    pending_user_deadline = NULL,
                    resolution_type = :resolution_type,
                    resolution_summary = :resolution_summary,
                    resolved_at = :resolved_at,
                    auto_close_at = :auto_close_at,
                    last_resolved_assignee_id = :last_resolved_assignee_id
                WHERE ticket_id = :ticket_id
                """
            ),
            {
                "resolution_type": resolution_type.value,
                "resolution_summary": resolution_summary,
                "resolved_at": as_mysql_utc(resolved_at),
                "auto_close_at": as_mysql_utc(auto_close_at),
                "last_resolved_assignee_id": last_resolved_assignee_id,
                "ticket_id": ticket_id,
            },
        )

    def get_resolved_snapshot(self, ticket_id: int) -> Mapping[str, Any] | None:
        """None when the ticket isn't RESOLVED -- same idempotency shape as
        get_pending_user_snapshot, for C019's auto-close.
        """
        row = self.get_ticket_for_update(ticket_id)
        if row is None or row["status_code"] != "RESOLVED":
            return None
        return row

    def apply_auto_close(self, *, ticket_id: int, closed_at: datetime) -> None:
        """C019.01-03: CLOSED + AUTO_AFTER_7_DAYS, resolution_* untouched."""
        self.database.execute(
            text(
                """
                UPDATE tickets
                SET status_code = 'CLOSED',
                    closure_type = :closure_type,
                    closed_at = :closed_at
                WHERE ticket_id = :ticket_id
                """
            ),
            {
                "closure_type": ClosureType.AUTO_AFTER_7_DAYS.value,
                "closed_at": as_mysql_utc(closed_at),
                "ticket_id": ticket_id,
            },
        )
