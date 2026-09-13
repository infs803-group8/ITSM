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

    def get_pending_user_timeout_candidates(
        self, *, now: datetime, limit: int, after_ticket_id: int = 0
    ) -> list[int]:
        """C036.02: bounded, keyset-paginated PENDING_USER tickets whose
        (single, shared) 120h User Timer has already expired as of ``now``
        -- candidates for DeadlineService.check_pending_user_timeout.
        Matches idx_tickets_pending_user_job (status_code,
        pending_user_deadline, ticket_id) exactly.
        """
        rows = self.database.execute(
            text(
                """
                SELECT ticket_id
                FROM tickets
                WHERE ticket_id > :after_ticket_id
                  AND status_code = 'PENDING_USER'
                  AND pending_user_deadline <= :now
                ORDER BY ticket_id
                LIMIT :limit
                """
            ),
            {"after_ticket_id": after_ticket_id, "now": as_mysql_utc(now), "limit": limit},
        ).all()
        return [int(row[0]) for row in rows]

    def get_auto_close_candidates(
        self, *, now: datetime, limit: int, after_ticket_id: int = 0
    ) -> list[int]:
        """C036.02: bounded, keyset-paginated RESOLVED tickets whose 7-day
        auto_close_at has already passed as of ``now`` -- candidates for
        DeadlineService.check_resolved_auto_close_timeout. Matches
        idx_tickets_auto_close_job (status_code, auto_close_at, ticket_id)
        exactly.
        """
        rows = self.database.execute(
            text(
                """
                SELECT ticket_id
                FROM tickets
                WHERE ticket_id > :after_ticket_id
                  AND status_code = 'RESOLVED'
                  AND auto_close_at <= :now
                ORDER BY ticket_id
                LIMIT :limit
                """
            ),
            {"after_ticket_id": after_ticket_id, "now": as_mysql_utc(now), "limit": limit},
        ).all()
        return [int(row[0]) for row in rows]

    def apply_initial_assignment(
        self, *, ticket_id: int, status: str, assignee_id: int | None
    ) -> None:
        """C023.02: fix the ticket's post-creation status/assignee.

        ``status`` is one of ``ASSIGNED``/``UNASSIGNED`` (a
        ``state_machine.TicketStatus`` value passed as a plain string by
        the caller) -- the ticket must never be left at the DB default of
        ``NEW`` once this transaction commits; ``chk_tickets_assignee_by_status``
        already enforces that ``ASSIGNED`` requires a non-null
        ``assignee_id`` and ``UNASSIGNED`` requires a null one, so passing
        a mismatched pair here fails loudly at the database rather than
        silently committing an inconsistent row.
        """
        self.database.execute(
            text(
                """
                UPDATE tickets
                SET status_code = :status, assignee_id = :assignee_id
                WHERE ticket_id = :ticket_id
                """
            ),
            {"status": status, "assignee_id": assignee_id, "ticket_id": ticket_id},
        )

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

    def get_ticket_state_row(self, ticket_id: int) -> Mapping[str, Any] | None:
        """``FOR UPDATE`` snapshot with everything needed to build
        ``state_machine.TicketState``, shared by every C025-C034 write-path
        action (Start, Request User Info, Resume, Escalate, Request
        Vendor, Vendor Response, Submit Resolution, Confirm Resolution,
        Reopen, Manual Close) via ``workflow/action_engine.lock_ticket_state``.

        Includes a few columns ``TicketState`` itself has no field for
        (``category_code``, and -- added for C033 -- ``last_resolved_
        assignee_id``) because several actions' own service layer reads
        them directly off ``locked.row`` for logic that sits above the
        pure state machine (C024/C028's target-engineer lookups,
        C033 Reopen's previous-assignee preference).
        """
        return (
            self.database.execute(
                text(
                    """
                    SELECT t.ticket_id, t.status_code, t.requester_id, t.assignee_id,
                           t.category_code, t.sla_cycle_no, t.sla_status_code,
                           t.sla_deadline, t.pending_user_reason, t.pending_user_deadline,
                           t.resolution_summary, t.resolution_type, t.resolved_at,
                           t.auto_close_at, t.closure_type, t.closed_at,
                           t.last_resolved_assignee_id,
                           assignee.role_code AS assignee_role_code
                    FROM tickets t
                    LEFT JOIN users assignee ON assignee.user_id = t.assignee_id
                    WHERE t.ticket_id = :ticket_id
                    FOR UPDATE
                    """
                ),
                {"ticket_id": ticket_id},
            )
            .mappings()
            .one_or_none()
        )

    def apply_status_change(self, *, ticket_id: int, status_code: str) -> None:
        """Narrow, single-column status update for actions whose
        ``TransitionResult.cycle_effect`` is ``KEEP`` and which touch no
        other column -- Start (C025) is the first and simplest of these.
        Actions that also change ``pending_user_*``/resolution/closure
        columns get their own, more specific repository methods instead
        of overloading this one with optional fields.
        """
        self.database.execute(
            text("UPDATE tickets SET status_code = :status_code WHERE ticket_id = :ticket_id"),
            {"status_code": status_code, "ticket_id": ticket_id},
        )

    def apply_pending_user_transition(
        self,
        *,
        ticket_id: int,
        status_code: str,
        pending_user_reason: PendingUserReason,
        pending_user_deadline: datetime,
    ) -> None:
        """C026.03/.04 (Request User Info): move the ticket into
        PENDING_USER with its reason/deadline set.

        No other column needs clearing here: ``chk_tickets_pending_user``
        only constrains ``pending_user_reason``/``pending_user_deadline``
        together with the status, and REQUEST_USER_INFO's only legal
        source state (IN_PROGRESS) never has a resolution/closure column
        populated to begin with, so there is nothing else on the row to
        touch. Per Q09's draft decision, this deliberately does NOT touch
        ``ticket_events`` -- any SLA_OVERDUE/SLA_AT_RISK history already
        written for the paused cycle stays exactly as it is.

        C031 (Submit Resolution) reaches PENDING_USER/RESOLUTION_
        CONFIRMATION too, but also needs to SET ``resolution_summary`` in
        the same UPDATE (``chk_tickets_resolution`` requires it non-null
        the moment ``pending_user_reason = 'RESOLUTION_CONFIRMATION'`` is
        set) -- see ``apply_submit_resolution`` below instead of
        overloading this method with an optional resolution field.
        """
        self.database.execute(
            text(
                """
                UPDATE tickets
                SET status_code = :status_code,
                    pending_user_reason = :pending_user_reason,
                    pending_user_deadline = :pending_user_deadline
                WHERE ticket_id = :ticket_id
                """
            ),
            {
                "status_code": status_code,
                "pending_user_reason": pending_user_reason.value,
                "pending_user_deadline": as_mysql_utc(pending_user_deadline),
                "ticket_id": ticket_id,
            },
        )

    def apply_submit_resolution(
        self,
        *,
        ticket_id: int,
        pending_user_deadline: datetime,
        resolution_summary: str,
    ) -> None:
        """C031: move the ticket to PENDING_USER/RESOLUTION_CONFIRMATION
        AND set ``resolution_summary`` in the same UPDATE --
        ``chk_tickets_resolution``'s middle branch requires
        ``resolution_summary IS NOT NULL`` together with
        ``pending_user_reason = 'RESOLUTION_CONFIRMATION'`` (and
        ``resolution_type``/``resolved_at``/``auto_close_at`` all still
        NULL at this point -- those are C032's job at Confirm
        Resolution), so this cannot reuse ``apply_pending_user_transition``
        as originally sketched in that method's own docstring.
        """
        self.database.execute(
            text(
                """
                UPDATE tickets
                SET status_code = 'PENDING_USER',
                    pending_user_reason = :pending_user_reason,
                    pending_user_deadline = :pending_user_deadline,
                    resolution_summary = :resolution_summary
                WHERE ticket_id = :ticket_id
                """
            ),
            {
                "pending_user_reason": PendingUserReason.RESOLUTION_CONFIRMATION.value,
                "pending_user_deadline": as_mysql_utc(pending_user_deadline),
                "resolution_summary": resolution_summary,
                "ticket_id": ticket_id,
            },
        )

    def apply_resume(self, *, ticket_id: int) -> None:
        """C027.03/.04 (Resume and Issue Persists share this single
        transition -- baseline §4.2/4.3 give both the identical effect):
        PENDING_USER -> IN_PROGRESS, clearing pending_user_reason/
        deadline. Also clears resolution_summary/resolution_type/
        resolved_at/auto_close_at unconditionally -- ``chk_tickets_
        resolution``'s third branch requires all four NULL for any status
        other than RESOLVED/CLOSED/PENDING_USER-with-RESOLUTION_
        CONFIRMATION, and IN_PROGRESS is such a status. This is a no-op
        for the INFORMATION_REQUIRED path (those columns are already
        NULL there) and the actual clear for the RESOLUTION_CONFIRMATION
        (Issue Persists) path -- C027.04's "清空当前待确认方案字段" -- the
        engineer's superseded resolution_summary is never carried forward
        into the new IN_PROGRESS cycle. Nothing in ticket_events is
        touched, so the RESOLUTION_SUBMITTED event for that superseded
        attempt (and any earlier SLA history) remains queryable exactly
        as C027.04's "保留历史" requires.
        """
        self.database.execute(
            text(
                """
                UPDATE tickets
                SET status_code = 'IN_PROGRESS',
                    pending_user_reason = NULL,
                    pending_user_deadline = NULL,
                    resolution_summary = NULL,
                    resolution_type = NULL,
                    resolved_at = NULL,
                    auto_close_at = NULL
                WHERE ticket_id = :ticket_id
                """
            ),
            {"ticket_id": ticket_id},
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

    def apply_confirm_resolution(
        self,
        *,
        ticket_id: int,
        resolution_type: str,
        resolved_at: datetime,
        auto_close_at: datetime,
        last_resolved_assignee_id: int | None,
    ) -> None:
        """C032: PENDING_USER/RESOLUTION_CONFIRMATION -> RESOLVED.
        ``resolution_summary`` was already written at Submit Resolution
        (C031) and is left untouched; this fills the columns
        ``chk_tickets_resolution``'s first branch additionally requires
        for RESOLVED/CLOSED (``resolution_type``, ``resolved_at``,
        ``auto_close_at``), clears ``pending_user_reason``/
        ``pending_user_deadline`` back to NULL (``chk_tickets_pending_
        user`` requires both NULL for any non-PENDING_USER status), and
        saves ``last_resolved_assignee_id`` -- the same column
        ``apply_auto_resolution`` (C018) already sets on its own
        RESOLVED path, read back by C033's Reopen to prefer this
        engineer if they are still available.
        """
        self.database.execute(
            text(
                """
                UPDATE tickets
                SET status_code = 'RESOLVED',
                    pending_user_reason = NULL,
                    pending_user_deadline = NULL,
                    resolution_type = :resolution_type,
                    resolved_at = :resolved_at,
                    auto_close_at = :auto_close_at,
                    last_resolved_assignee_id = :last_resolved_assignee_id
                WHERE ticket_id = :ticket_id
                """
            ),
            {
                "resolution_type": resolution_type,
                "resolved_at": as_mysql_utc(resolved_at),
                "auto_close_at": as_mysql_utc(auto_close_at),
                "last_resolved_assignee_id": last_resolved_assignee_id,
                "ticket_id": ticket_id,
            },
        )

    def apply_reopen(self, *, ticket_id: int, assignee_id: int | None) -> None:
        """C033: RESOLVED -> REOPENED. Clears the four resolution/closure-
        window columns back to NULL (``chk_tickets_resolution``'s third
        branch requires all of them NULL once status leaves RESOLVED/
        CLOSED and PENDING_USER/RESOLUTION_CONFIRMATION) but deliberately
        leaves ``last_resolved_assignee_id`` untouched -- it is C033's own
        INPUT (read by the caller before this call to decide
        ``assignee_id``), not something this action itself produces, and
        it will only be overwritten the next time this ticket resolves.
        ``assignee_id`` may be the same previous assignee, a freshly
        auto-picked one, or ``None`` (``chk_tickets_assignee_by_status``
        places no constraint on ``assignee_id`` for REOPENED, unlike
        ASSIGNED/IN_PROGRESS/PENDING_USER/PENDING_VENDOR).
        """
        self.database.execute(
            text(
                """
                UPDATE tickets
                SET status_code = 'REOPENED',
                    assignee_id = :assignee_id,
                    resolution_summary = NULL,
                    resolution_type = NULL,
                    resolved_at = NULL,
                    auto_close_at = NULL
                WHERE ticket_id = :ticket_id
                """
            ),
            {"assignee_id": assignee_id, "ticket_id": ticket_id},
        )

    def apply_manual_close(self, *, ticket_id: int, closed_at: datetime) -> None:
        """C034: RESOLVED -> CLOSED. Touches only ``status_code``/
        ``closure_type``/``closed_at`` -- ``chk_tickets_resolution``'s
        first branch already holds for RESOLVED and CLOSED alike, so the
        resolution_* columns Confirm Resolution (C032) wrote stay exactly
        as they are.
        """
        self.database.execute(
            text(
                """
                UPDATE tickets
                SET status_code = 'CLOSED',
                    closure_type = 'MANUAL_USER',
                    closed_at = :closed_at
                WHERE ticket_id = :ticket_id
                """
            ),
            {"closed_at": as_mysql_utc(closed_at), "ticket_id": ticket_id},
        )
