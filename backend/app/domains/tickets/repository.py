"""Ticket persistence and role-scoped read queries."""

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.common.request_context import RequestContext
from app.core.enums import UserRole
from app.domains.tickets.model import Ticket


class TicketRepository:
    def __init__(self, database: Session) -> None:
        self.database = database

    @staticmethod
    def scope_sql(actor: RequestContext, alias: str = "t") -> tuple[str, dict[str, Any]]:
        if actor.role == UserRole.SERVICE_DESK_MANAGER:
            return "1 = 1", {}
        if actor.role == UserRole.USER:
            return f"{alias}.requester_id = :actor_id", {"actor_id": actor.user_id}
        if actor.role in {UserRole.ENGINEER_TIER1, UserRole.ENGINEER_TIER2}:
            return f"{alias}.assignee_id = :actor_id", {"actor_id": actor.user_id}
        if actor.role == UserRole.EXTERNAL_VENDOR and actor.vendor_org_id is not None:
            return (
                f"EXISTS (SELECT 1 FROM vendor_requests scope_vr "
                f"WHERE scope_vr.ticket_id = {alias}.ticket_id "
                "AND scope_vr.vendor_org_id = :vendor_org_id)",
                {"vendor_org_id": actor.vendor_org_id},
            )
        return "0 = 1", {}

    @staticmethod
    def _projection() -> str:
        return """
            t.*, requester.display_name AS requester_name,
            assignee.display_name AS assignee_name,
            assignee.role_code AS assignee_role,
            assignee.is_available AS assignee_available,
            COALESCE(skills.skill_codes, '') AS assignee_skills,
            COALESCE(loads.active_load, 0) AS assignee_active_load,
            vr.vendor_request_id, vr.vendor_org_id AS request_vendor_org_id,
            vr.status AS vendor_request_status, vr.vendor_message,
            vr.created_at AS vendor_request_created_at, vr.responded_at,
            vo.name AS vendor_org_name, vo.is_active AS vendor_org_active
        """

    @staticmethod
    def _joins(actor: RequestContext) -> str:
        vendor_filter = (
            "AND vr2.vendor_org_id = :vendor_org_id"
            if actor.role == UserRole.EXTERNAL_VENDOR
            else ""
        )
        return f"""
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
                                      'PENDING_VENDOR', 'REOPENED')
                GROUP BY assignee_id
            ) loads ON loads.assignee_id = assignee.user_id
            LEFT JOIN vendor_requests vr
              ON vr.ticket_id = t.ticket_id
             AND vr.vendor_request_id = (
                 SELECT MAX(vr2.vendor_request_id) FROM vendor_requests vr2
                 WHERE vr2.ticket_id = t.ticket_id
                 {vendor_filter}
             )
            LEFT JOIN vendor_organisations vo ON vo.vendor_org_id = vr.vendor_org_id
        """

    def create(
        self,
        *,
        requester_id: int,
        title: str,
        description: str,
        category: str,
        priority: str,
    ) -> Ticket:
        ticket = Ticket(
            requester_id=requester_id,
            title=title,
            description=description,
            category_code=category,
            priority_code=priority,
            status_code="NEW",
        )
        self.database.add(ticket)
        self.database.flush()
        return ticket

    def get_model(self, ticket_id: int, *, for_update: bool = False) -> Ticket | None:
        statement = select(Ticket).where(Ticket.ticket_id == ticket_id)
        if for_update:
            statement = statement.with_for_update()
        return self.database.execute(statement).scalar_one_or_none()

    def visible(self, actor: RequestContext, ticket_id: int) -> bool:
        scope, params = self.scope_sql(actor)
        params["ticket_id"] = ticket_id
        return (
            self.database.execute(
                text(f"SELECT 1 FROM tickets t WHERE t.ticket_id=:ticket_id AND {scope}"),
                params,
            ).scalar_one_or_none()
            is not None
        )

    def detail(
        self,
        actor: RequestContext,
        ticket_id: int,
        *,
        visibility_already_authorized: bool = False,
    ) -> Mapping[str, Any] | None:
        """Role-scoped detail row.

        ``visibility_already_authorized`` skips ONLY the ticket-level scope
        predicate, for a post-write response whose action already checked
        visibility and permission before it ran (see
        ``detail_assembler.assemble_ticket_detail``). The Vendor join filter
        still applies, so a Vendor never sees another organisation's request.
        """
        if visibility_already_authorized:
            scope, params = "1 = 1", {}
            if actor.role == UserRole.EXTERNAL_VENDOR:
                params["vendor_org_id"] = actor.vendor_org_id
        else:
            scope, params = self.scope_sql(actor)
        params["ticket_id"] = ticket_id
        return self.database.execute(
            text(
                f"SELECT {self._projection()} FROM tickets t {self._joins(actor)} "
                f"WHERE t.ticket_id=:ticket_id AND {scope}"
            ),
            params,
        ).mappings().one_or_none()

    def list(
        self,
        actor: RequestContext,
        *,
        page: int,
        page_size: int,
        statuses: Sequence[str] | None,
        category: str | None,
        priority: str | None,
        sla_status: str | None,
        assignee_id: int | None,
        search: str | None,
        sort_by: str,
        sort_order: str,
    ) -> tuple[Sequence[Mapping[str, Any]], int]:
        scope, params = self.scope_sql(actor)
        filters = [scope]
        if statuses and actor.role == UserRole.EXTERNAL_VENDOR:
            visible_status = statuses[0]
            if visible_status == "CLOSED":
                filters.append("t.status_code = 'CLOSED'")
            elif visible_status == "PENDING_VENDOR":
                filters.append("t.status_code <> 'CLOSED' AND vr.status = 'ACTIVE'")
            elif visible_status == "IN_PROGRESS":
                filters.append(
                    "t.status_code <> 'CLOSED' AND (vr.status IS NULL OR vr.status <> 'ACTIVE')"
                )
        elif statuses:
            status_parameters: list[str] = []
            for index, value in enumerate(statuses):
                key = f"status_{index}"
                status_parameters.append(f":{key}")
                params[key] = value
            filters.append(f"t.status_code IN ({', '.join(status_parameters)})")
        for column, value, key in (
            ("t.category_code", category, "category"),
            ("t.priority_code", priority, "priority"),
            ("t.sla_status_code", sla_status, "sla_status"),
            ("t.assignee_id", assignee_id, "assignee_id"),
        ):
            if value is not None:
                filters.append(f"{column} = :{key}")
                params[key] = value
        if search is not None:
            filters.append("t.title LIKE :search")
            params["search"] = f"%{search}%"
        params.update({"limit": page_size, "offset": (page - 1) * page_size})
        where = " AND ".join(filters)
        total = int(
            self.database.execute(
                text(
                    f"SELECT COUNT(*) FROM tickets t {self._joins(actor)} WHERE {where}"
                ),
                params,
            ).scalar_one()
        )
        sort_columns = {
            "created_at": "t.created_at",
            "updated_at": "t.updated_at",
            "sla_deadline": "t.sla_deadline",
            "priority": "FIELD(t.priority_code, 'LOW','MEDIUM','HIGH','URGENT')",
        }
        order = "ASC" if sort_order == "asc" else "DESC"
        rows = self.database.execute(
            text(
                f"SELECT {self._projection()} FROM tickets t {self._joins(actor)} "
                f"WHERE {where} ORDER BY {sort_columns[sort_by]} {order}, "
                f"t.ticket_id {order} LIMIT :limit OFFSET :offset"
            ),
            params,
        ).mappings().all()
        return rows, total

    def flush(self) -> None:
        self.database.flush()
