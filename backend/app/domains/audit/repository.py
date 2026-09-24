"""Append and query access to the append-only ``ticket_events`` table.

``list_events`` joins into the plain ``users`` table with raw SQL (same
pattern as ``app.domains.dashboard.repository``) rather than through a
User ORM relationship, since Member B's User model is not registered yet.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.common.request_context import RequestContext
from app.domains.audit.access_policy import TicketAccessRecord
from app.domains.audit.model import TicketEvent


class AuditRepository:
    def __init__(self, database: Session) -> None:
        self.database = database

    def get_ticket_access(
        self,
        ticket_id: int,
        actor: RequestContext,
    ) -> TicketAccessRecord | None:
        row = (
            self.database.execute(
                text(
                    """
                SELECT t.ticket_id, t.requester_id, t.assignee_id, t.status_code,
                       active_vr.vendor_request_id AS active_vendor_request_id,
                       active_vr.vendor_org_id AS active_vendor_org_id,
                       EXISTS(
                           SELECT 1 FROM vendor_requests history_vr
                           WHERE history_vr.ticket_id = t.ticket_id
                             AND history_vr.vendor_org_id = :actor_vendor_org_id
                       ) AS actor_has_vendor_history
                FROM tickets t
                LEFT JOIN vendor_requests active_vr
                  ON active_vr.ticket_id = t.ticket_id AND active_vr.status = 'ACTIVE'
                WHERE t.ticket_id = :ticket_id
                """
                ),
                {"ticket_id": ticket_id, "actor_vendor_org_id": actor.vendor_org_id or 0},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return TicketAccessRecord(
            ticket_id=int(row["ticket_id"]),
            requester_id=int(row["requester_id"]),
            assignee_id=int(row["assignee_id"]) if row["assignee_id"] is not None else None,
            status_code=str(row["status_code"]),
            active_vendor_request_id=(
                int(row["active_vendor_request_id"])
                if row["active_vendor_request_id"] is not None
                else None
            ),
            active_vendor_org_id=(
                int(row["active_vendor_org_id"])
                if row["active_vendor_org_id"] is not None
                else None
            ),
            actor_has_vendor_history=bool(row["actor_has_vendor_history"]),
        )

    def append(
        self,
        *,
        ticket_id: int,
        event_type: str,
        scope: str,
        actor_id: int | None,
        vendor_org_id: int | None = None,
        cycle_no: int | None = None,
        comment_id: int | None = None,
        attachment_id: str | None = None,
        vendor_request_id: int | None = None,
        metadata: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> TicketEvent:
        """Stage one append-only event row.

        Only calls ``add``/``flush`` -- never ``commit`` -- so this shares
        the caller's own transaction. The DB-level
        ``uq_ticket_events_cycle_guard`` constraint (schema.sql) makes
        repeated SLA-cycle writes idempotent across job re-runs; a
        duplicate write raises ``IntegrityError``, which callers that
        re-run jobs should catch and treat as already-recorded.
        """
        event = TicketEvent(
            ticket_id=ticket_id,
            event_type=event_type,
            scope=scope,
            actor_id=actor_id,
            vendor_org_id=vendor_org_id,
            cycle_no=cycle_no,
            comment_id=comment_id,
            attachment_id=attachment_id,
            vendor_request_id=vendor_request_id,
            metadata_json=metadata or {},
        )
        if occurred_at is not None:
            event.occurred_at = occurred_at
        self.database.add(event)
        self.database.flush()
        return event

    def list_events(
        self,
        *,
        ticket_id: int,
        allowed_scopes: Sequence[str],
        vendor_org_id: int | None,
        event_type: str | None,
        scope: str | None,
        page: int,
        page_size: int,
    ) -> tuple[Sequence[Mapping[str, Any]], int]:
        filters = ["e.ticket_id = :ticket_id", "e.scope IN :allowed_scopes"]
        params: dict[str, Any] = {
            "ticket_id": ticket_id,
            "allowed_scopes": tuple(allowed_scopes),
        }
        if vendor_org_id is not None:
            filters.append("(e.scope <> 'VENDOR_SCOPE' OR e.vendor_org_id = :vendor_org_id)")
            params["vendor_org_id"] = vendor_org_id
        if event_type is not None:
            filters.append("e.event_type = :event_type")
            params["event_type"] = event_type
        if scope is not None:
            filters.append("e.scope = :scope")
            params["scope"] = scope
        where_sql = " AND ".join(filters)
        bind_params = [bindparam("allowed_scopes", expanding=True)]

        count = int(
            self.database.execute(
                text(f"SELECT COUNT(*) FROM ticket_events e WHERE {where_sql}").bindparams(
                    *bind_params
                ),
                params,
            ).scalar_one()
        )
        rows = (
            self.database.execute(
                text(
                    f"""
                SELECT e.event_id, e.ticket_id, e.event_type, e.scope,
                       e.actor_id, u.display_name AS actor_display_name,
                       u.role_code AS actor_role,
                       e.cycle_no, e.occurred_at, e.metadata
                FROM ticket_events e
                LEFT JOIN users u ON u.user_id = e.actor_id
                WHERE {where_sql}
                ORDER BY e.occurred_at DESC, e.event_id DESC
                LIMIT :limit OFFSET :offset
                """
                ).bindparams(*bind_params),
                {**params, "limit": page_size, "offset": (page - 1) * page_size},
            )
            .mappings()
            .all()
        )
        return rows, count
