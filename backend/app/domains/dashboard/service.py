"""Role-scoped dashboard orchestration."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.common.pagination import PaginationMeta
from app.common.request_context import RequestContext
from app.core.clock import as_utc
from app.core.enums import Category, Priority, TicketStatus, UserRole
from app.core.errors import ApplicationError
from app.domains.dashboard.repository import DashboardRepository
from app.domains.dashboard.schema import (
    ActionRequiredCounts,
    AssigneeSummary,
    DashboardCounts,
    DashboardSummaryData,
    DashboardSummaryResponse,
    EngineerTier,
    OverdueListResponse,
    OverdueMeta,
    OverdueMode,
    OverdueTicket,
    SlaCounts,
)

ALLOWED_ROLES = {
    UserRole.ENGINEER_TIER1,
    UserRole.ENGINEER_TIER2,
    UserRole.SERVICE_DESK_MANAGER,
}


class DashboardService:
    def __init__(self, database: Session) -> None:
        self.repository = DashboardRepository(database)

    @staticmethod
    def _authorise(actor: RequestContext) -> None:
        if actor.role not in ALLOWED_ROLES:
            raise ApplicationError(
                "DATA_SCOPE_DENIED",
                "Dashboard access is limited to engineers and service desk managers.",
                403,
            )

    @staticmethod
    def _number(row: object) -> int:
        return int(row or 0)

    def summary(self, actor: RequestContext) -> DashboardSummaryResponse:
        self._authorise(actor)
        row = self.repository.summary(actor)
        return DashboardSummaryResponse(
            data=DashboardSummaryData(
                scope=self.repository.scope(actor),
                generated_at=datetime.now(UTC),
                counts=DashboardCounts(
                    total_active=self._number(row["total_active"]),
                    unassigned=self._number(row["unassigned"]),
                    assigned=self._number(row["assigned"]),
                    in_progress=self._number(row["in_progress"]),
                    pending_user=self._number(row["pending_user"]),
                    pending_vendor=self._number(row["pending_vendor"]),
                    resolved=self._number(row["resolved"]),
                    reopened=self._number(row["reopened"]),
                    closed=self._number(row["closed"]),
                ),
                sla=SlaCounts(
                    at_risk=self._number(row["at_risk"]),
                    overdue=self._number(row["overdue"]),
                ),
                action_required=ActionRequiredCounts(
                    reopened_unassigned=self._number(row["reopened_unassigned"])
                ),
            )
        )

    @staticmethod
    def _assignee(row: Mapping[str, Any]) -> AssigneeSummary | None:
        if row["assignee_user_id"] is None:
            return None
        role = str(row["assignee_role"])
        tier = EngineerTier.TIER1 if role == UserRole.ENGINEER_TIER1 else EngineerTier.TIER2
        raw_skills = str(row["skill_codes"] or "")
        return AssigneeSummary(
            user_id=int(row["assignee_user_id"]),
            display_name=str(row["assignee_name"]),
            tier=tier,
            skills=[Category(item) for item in raw_skills.split(",") if item],
            is_available=bool(row["is_available"]),
            active_load=int(row["active_load"] or 0),
        )

    def overdue(
        self,
        actor: RequestContext,
        *,
        mode: OverdueMode,
        page: int,
        page_size: int,
        category: Category | None,
        priority: Priority | None,
    ) -> OverdueListResponse:
        self._authorise(actor)
        rows, total = self.repository.list_overdue(
            actor,
            mode=mode,
            page=page,
            page_size=page_size,
            category=category,
            priority=priority,
        )
        data = [
            OverdueTicket(
                ticket_id=int(row["ticket_id"]),
                title=str(row["title"]),
                category=Category(str(row["category_code"])),
                priority=Priority(str(row["priority_code"])),
                status=TicketStatus(str(row["status_code"])),
                display_status=str(row["status_code"]),
                assignee=self._assignee(row),
                sla_cycle_no=int(row["sla_cycle_no"]),
                sla_deadline=as_utc(row["sla_deadline"]),
                overdue_at=as_utc(row["overdue_at"]),
                is_current=bool(row["is_current"]),
            )
            for row in rows
        ]
        pagination = PaginationMeta.from_total(page=page, page_size=page_size, total=total)
        return OverdueListResponse(
            data=data,
            meta=OverdueMeta(**pagination.model_dump(), mode=mode),
        )
