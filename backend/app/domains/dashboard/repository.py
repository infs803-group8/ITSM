"""Read-only SQL queries for the dashboard."""

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.common.request_context import RequestContext
from app.core.enums import Category, Priority, UserRole
from app.domains.dashboard.schema import DashboardScope, OverdueMode


class DashboardRepository:
    def __init__(self, database: Session) -> None:
        self.database = database

    @staticmethod
    def scope(actor: RequestContext) -> DashboardScope:
        if actor.role == UserRole.SERVICE_DESK_MANAGER:
            return DashboardScope.GLOBAL
        return DashboardScope.MY_ASSIGNED

    @staticmethod
    def _scope_sql(actor: RequestContext, alias: str = "t") -> tuple[str, dict[str, Any]]:
        if actor.role == UserRole.SERVICE_DESK_MANAGER:
            return "1 = 1", {}
        return f"{alias}.assignee_id = :actor_id", {"actor_id": actor.user_id}

    def summary(self, actor: RequestContext) -> Mapping[str, Any]:
        scope_sql, params = self._scope_sql(actor)
        return self.database.execute(
            text(
                f"""
                SELECT
                  SUM(t.status_code NOT IN ('RESOLVED', 'CLOSED', 'NEW')) AS total_active,
                  SUM(t.status_code = 'UNASSIGNED') AS unassigned,
                  SUM(t.status_code = 'ASSIGNED') AS assigned,
                  SUM(t.status_code = 'IN_PROGRESS') AS in_progress,
                  SUM(t.status_code = 'PENDING_USER') AS pending_user,
                  SUM(t.status_code = 'PENDING_VENDOR') AS pending_vendor,
                  SUM(t.status_code = 'RESOLVED') AS resolved,
                  SUM(t.status_code = 'REOPENED') AS reopened,
                  SUM(t.status_code = 'CLOSED') AS closed,
                  SUM(t.sla_status_code = 'AT_RISK'
                      AND t.status_code NOT IN ('RESOLVED', 'CLOSED')) AS at_risk,
                  SUM(t.sla_status_code = 'OVERDUE'
                      AND t.status_code NOT IN ('RESOLVED', 'CLOSED')) AS overdue,
                  SUM(t.status_code = 'REOPENED' AND t.assignee_id IS NULL)
                    AS reopened_unassigned
                FROM tickets t
                WHERE {scope_sql}
                """
            ),
            params,
        ).mappings().one()

    def list_overdue(
        self,
        actor: RequestContext,
        *,
        mode: OverdueMode,
        page: int,
        page_size: int,
        category: Category | None,
        priority: Priority | None,
    ) -> tuple[Sequence[Mapping[str, Any]], int]:
        scope_sql, params = self._scope_sql(actor)
        filters = [scope_sql]
        if category is not None:
            filters.append("t.category_code = :category")
            params["category"] = category.value
        if priority is not None:
            filters.append("t.priority_code = :priority")
            params["priority"] = priority.value
        params.update({"limit": page_size, "offset": (page - 1) * page_size})
        where_sql = " AND ".join(filters)

        if mode == OverdueMode.CURRENT:
            overdue_where = (
                f"{where_sql} AND t.sla_status_code = 'OVERDUE' "
                "AND t.status_code NOT IN ('RESOLVED', 'CLOSED')"
            )
            count = int(
                self.database.execute(
                    text(f"SELECT COUNT(*) FROM tickets t WHERE {overdue_where}"), params
                ).scalar_one()
            )
            rows = self.database.execute(
                text(
                    f"""
                    SELECT t.ticket_id, t.title, t.category_code, t.priority_code,
                           t.status_code, t.sla_cycle_no, t.sla_deadline,
                           COALESCE(overdue_event.occurred_at, t.sla_deadline) AS overdue_at,
                           1 AS is_current,
                           u.user_id AS assignee_user_id, u.display_name AS assignee_name,
                           u.role_code AS assignee_role, u.is_available,
                           COALESCE(skills.skill_codes, '') AS skill_codes,
                           COALESCE(loads.active_load, 0) AS active_load
                    FROM tickets t
                    LEFT JOIN users u ON u.user_id = t.assignee_id
                    LEFT JOIN (
                        SELECT user_id, GROUP_CONCAT(category_code ORDER BY category_code)
                          AS skill_codes
                        FROM user_skills GROUP BY user_id
                    ) skills ON skills.user_id = u.user_id
                    LEFT JOIN (
                        SELECT assignee_id, COUNT(*) AS active_load FROM tickets
                        WHERE status_code IN ('ASSIGNED', 'IN_PROGRESS',
                                              'PENDING_USER', 'PENDING_VENDOR')
                        GROUP BY assignee_id
                    ) loads ON loads.assignee_id = u.user_id
                    LEFT JOIN ticket_events overdue_event
                      ON overdue_event.ticket_id = t.ticket_id
                     AND overdue_event.cycle_no = t.sla_cycle_no
                     AND overdue_event.event_type = 'SLA_OVERDUE'
                    WHERE {overdue_where}
                    ORDER BY overdue_at DESC, t.ticket_id DESC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                params,
            ).mappings().all()
            return rows, count

        history_where = f"{where_sql} AND e.event_type = 'SLA_OVERDUE'"
        count = int(
            self.database.execute(
                text(
                    "SELECT COUNT(*) FROM ticket_events e "
                    "JOIN tickets t ON t.ticket_id = e.ticket_id "
                    f"WHERE {history_where}"
                ),
                params,
            ).scalar_one()
        )
        rows = self.database.execute(
            text(
                f"""
                SELECT t.ticket_id, t.title, t.category_code, t.priority_code,
                       t.status_code, e.cycle_no AS sla_cycle_no,
                       COALESCE(
                         STR_TO_DATE(
                           JSON_UNQUOTE(JSON_EXTRACT(e.metadata, '$.sla_deadline')),
                           '%Y-%m-%dT%H:%i:%s.%fZ'
                         ),
                         t.sla_deadline,
                         e.occurred_at
                       ) AS sla_deadline,
                       e.occurred_at AS overdue_at,
                       (t.sla_cycle_no = e.cycle_no
                        AND t.sla_status_code = 'OVERDUE'
                        AND t.status_code NOT IN ('RESOLVED', 'CLOSED')) AS is_current,
                       u.user_id AS assignee_user_id, u.display_name AS assignee_name,
                       u.role_code AS assignee_role, u.is_available,
                       COALESCE(skills.skill_codes, '') AS skill_codes,
                       COALESCE(loads.active_load, 0) AS active_load
                FROM ticket_events e
                JOIN tickets t ON t.ticket_id = e.ticket_id
                LEFT JOIN users u ON u.user_id = t.assignee_id
                LEFT JOIN (
                    SELECT user_id, GROUP_CONCAT(category_code ORDER BY category_code)
                      AS skill_codes
                    FROM user_skills GROUP BY user_id
                ) skills ON skills.user_id = u.user_id
                LEFT JOIN (
                    SELECT assignee_id, COUNT(*) AS active_load FROM tickets
                    WHERE status_code IN ('ASSIGNED', 'IN_PROGRESS',
                                          'PENDING_USER', 'PENDING_VENDOR')
                    GROUP BY assignee_id
                ) loads ON loads.assignee_id = u.user_id
                WHERE {history_where}
                ORDER BY e.occurred_at DESC, e.event_id DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        ).mappings().all()
        return rows, count
