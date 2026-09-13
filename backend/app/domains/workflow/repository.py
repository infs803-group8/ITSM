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
from app.domains.workflow.state_machine import ClosureType, PendingUserReason, ResolutionType


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

    def get_workflow_snapshot(self, ticket_id: int) -> Mapping[str, Any] | None:
        """Read-only ticket + requester + assignee snapshot for C021's
        ``WorkflowReadModel``. Unlike ``get_ticket_for_update`` this is a
        plain SELECT (no ``FOR UPDATE``) since a GET must never take a
        row lock, and it carries the extra display fields (names, tier,
        skills, availability, active load) that only a read path needs.

        ``active_load`` reuses the exact definition already established by
        ``app.domains.dashboard.repository``: tickets currently assigned to
        that engineer in a non-terminal, non-unassigned status.
        """
        return (
            self.database.execute(
                text(
                    """
                    SELECT t.ticket_id, t.status_code, t.requester_id, t.assignee_id,
                           t.sla_cycle_no, t.sla_status_code, t.sla_started_at,
                           t.sla_deadline, t.pending_user_reason, t.pending_user_deadline,
                           t.resolution_summary, t.resolution_type, t.resolved_at,
                           t.auto_close_at, t.closure_type, t.closed_at,
                           requester.display_name AS requester_display_name,
                           assignee.user_id AS assignee_user_id,
                           assignee.display_name AS assignee_display_name,
                           assignee.role_code AS assignee_role_code,
                           assignee.is_available AS assignee_is_available,
                           COALESCE(skills.skill_codes, '') AS assignee_skill_codes,
                           COALESCE(loads.active_load, 0) AS assignee_active_load
                    FROM tickets t
                    JOIN users requester ON requester.user_id = t.requester_id
                    LEFT JOIN users assignee ON assignee.user_id = t.assignee_id
                    LEFT JOIN (
                        SELECT user_id, GROUP_CONCAT(category_code ORDER BY category_code)
                          AS skill_codes
                        FROM user_skills GROUP BY user_id
                    ) skills ON skills.user_id = assignee.user_id
                    LEFT JOIN (
                        SELECT assignee_id, COUNT(*) AS active_load FROM tickets
                        WHERE status_code IN ('ASSIGNED', 'IN_PROGRESS',
                                              'PENDING_USER', 'PENDING_VENDOR')
                        GROUP BY assignee_id
                    ) loads ON loads.assignee_id = assignee.user_id
                    WHERE t.ticket_id = :ticket_id
                    """
                ),
                {"ticket_id": ticket_id},
            )
            .mappings()
            .one_or_none()
        )

    def get_latest_vendor_request(self, ticket_id: int) -> Mapping[str, Any] | None:
        """The most recently created vendor request for this ticket, whatever
        its status -- Q03 (decision log, draft): ``TicketDetail.vendor_request``
        exposes only the single "current" request, not the full history; a
        dedicated history endpoint is a separate, not-yet-agreed change.
        """
        return (
            self.database.execute(
                text(
                    """
                    SELECT vr.vendor_request_id, vr.vendor_org_id, vr.vendor_message,
                           vr.status, vr.created_at, vr.responded_at,
                           org.name AS vendor_org_name, org.is_active AS vendor_org_is_active
                    FROM vendor_requests vr
                    JOIN vendor_organisations org ON org.vendor_org_id = vr.vendor_org_id
                    WHERE vr.ticket_id = :ticket_id
                    ORDER BY vr.created_at DESC, vr.vendor_request_id DESC
                    LIMIT 1
                    """
                ),
                {"ticket_id": ticket_id},
            )
            .mappings()
            .one_or_none()
        )

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
