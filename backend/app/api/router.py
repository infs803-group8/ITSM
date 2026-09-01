"""Top-level API router."""

from fastapi import APIRouter

from app.domains.assignment.router import router as assignment_router
from app.domains.attachments.router import router as attachments_router
from app.domains.audit.router import router as audit_router
from app.domains.auth.router import router as auth_router
from app.domains.comments.router import router as comments_router
from app.domains.dashboard.router import router as dashboard_router
from app.domains.platform.router import router as platform_router
from app.domains.reference_data.router import router as reference_data_router
from app.domains.tickets.router import router as tickets_router
from app.domains.users.router import router as users_router
from app.domains.vendor_workflow.router import router as vendor_workflow_router
from app.domains.workflow.router import router as workflow_router

api_router = APIRouter()
for domain_router in (
    platform_router,
    attachments_router,
    dashboard_router,
    auth_router,
    users_router,
    reference_data_router,
    tickets_router,
    comments_router,
    assignment_router,
    workflow_router,
    vendor_workflow_router,
    audit_router,
):
    api_router.include_router(domain_router)
