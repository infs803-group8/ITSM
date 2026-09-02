"""Pydantic contract for API-06 and API-07."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.core.enums import Category, Priority, TicketStatus


class DashboardScope(StrEnum):
    GLOBAL = "GLOBAL"
    MY_ASSIGNED = "MY_ASSIGNED"


class OverdueMode(StrEnum):
    CURRENT = "current"
    HISTORY = "history"


class EngineerTier(StrEnum):
    TIER1 = "TIER1"
    TIER2 = "TIER2"


class AssigneeSummary(BaseModel):
    user_id: int
    display_name: str
    tier: EngineerTier
    skills: list[Category]
    is_available: bool
    active_load: int = Field(ge=0)


class DashboardCounts(BaseModel):
    total_active: int = Field(ge=0)
    unassigned: int = Field(ge=0)
    assigned: int = Field(ge=0)
    in_progress: int = Field(ge=0)
    pending_user: int = Field(ge=0)
    pending_vendor: int = Field(ge=0)
    resolved: int = Field(ge=0)
    reopened: int = Field(ge=0)
    closed: int = Field(ge=0)


class SlaCounts(BaseModel):
    at_risk: int = Field(ge=0)
    overdue: int = Field(ge=0)


class ActionRequiredCounts(BaseModel):
    reopened_unassigned: int = Field(ge=0)


class DashboardSummaryData(BaseModel):
    scope: DashboardScope
    generated_at: datetime
    counts: DashboardCounts
    sla: SlaCounts
    action_required: ActionRequiredCounts


class DashboardSummaryResponse(BaseModel):
    data: DashboardSummaryData


class OverdueTicket(BaseModel):
    ticket_id: int
    title: str
    category: Category
    priority: Priority
    status: TicketStatus
    display_status: str
    assignee: AssigneeSummary | None
    sla_cycle_no: int = Field(ge=1)
    sla_deadline: datetime
    overdue_at: datetime
    is_current: bool


class OverdueMeta(BaseModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)
    mode: OverdueMode


class OverdueListResponse(BaseModel):
    data: list[OverdueTicket]
    meta: OverdueMeta
