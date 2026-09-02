from datetime import UTC, datetime, timedelta

import pytest

from app.common.request_context import RequestContext
from app.core.enums import UserRole
from app.core.errors import ApplicationError
from app.domains.dashboard.schema import DashboardScope, OverdueMode
from app.domains.dashboard.service import DashboardService


class DashboardRepositoryFake:
    def scope(self, actor):
        if actor.role == UserRole.SERVICE_DESK_MANAGER:
            return DashboardScope.GLOBAL
        return DashboardScope.MY_ASSIGNED

    def summary(self, _actor):
        return {
            "total_active": 5,
            "unassigned": 1,
            "assigned": 1,
            "in_progress": 2,
            "pending_user": 0,
            "pending_vendor": 0,
            "resolved": 1,
            "reopened": 1,
            "closed": 3,
            "at_risk": 2,
            "overdue": 1,
            "reopened_unassigned": 1,
        }

    def list_overdue(self, _actor, **_kwargs):
        now = datetime.now(UTC)
        return [
            {
                "ticket_id": 42,
                "title": "VPN unavailable",
                "category_code": "NETWORK",
                "priority_code": "HIGH",
                "status_code": "IN_PROGRESS",
                "sla_cycle_no": 1,
                "sla_deadline": now - timedelta(hours=2),
                "overdue_at": now - timedelta(hours=2),
                "is_current": 1,
                "assignee_user_id": 2,
                "assignee_name": "Tier 1 Engineer",
                "assignee_role": "ENGINEER_TIER1",
                "is_available": 1,
                "skill_codes": "NETWORK,SOFTWARE",
                "active_load": 3,
            }
        ], 1


def dashboard_service():
    service = DashboardService(None)
    service.repository = DashboardRepositoryFake()
    return service


def test_manager_gets_global_dashboard_summary():
    response = dashboard_service().summary(
        RequestContext(user_id=9, role=UserRole.SERVICE_DESK_MANAGER)
    )
    assert response.data.scope == "GLOBAL"
    assert response.data.counts.total_active == 5
    assert response.data.sla.overdue == 1
    assert response.data.action_required.reopened_unassigned == 1


def test_requester_cannot_open_dashboard():
    with pytest.raises(ApplicationError) as error:
        dashboard_service().summary(RequestContext(user_id=1, role=UserRole.USER))
    assert error.value.code == "DATA_SCOPE_DENIED"
    assert error.value.status_code == 403


def test_engineer_overdue_list_is_contract_shaped():
    response = dashboard_service().overdue(
        RequestContext(user_id=2, role=UserRole.ENGINEER_TIER1),
        mode=OverdueMode.CURRENT,
        page=1,
        page_size=20,
        category=None,
        priority=None,
    )
    assert response.meta.mode == "current"
    assert response.meta.total == 1
    assert response.data[0].assignee.tier == "TIER1"
    assert response.data[0].assignee.skills == ["NETWORK", "SOFTWARE"]
