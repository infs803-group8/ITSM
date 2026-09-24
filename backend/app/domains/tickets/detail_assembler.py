"""Single role-aware assembler for public ticket detail and summary views."""

from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from app.common.request_context import RequestContext
from app.core.clock import as_utc
from app.core.enums import AvailableAction, Category, Priority, TicketStatus, UserRole
from app.domains.tickets.repository import TicketRepository
from app.domains.tickets.schema import TicketDetail, TicketSummary
from app.domains.workflow.read_model import WorkflowReadModel
from app.domains.workflow.serializer import ActorContext


def _actor_context(actor: RequestContext) -> ActorContext:
    return ActorContext(
        role=UserRole(actor.role),
        user_id=actor.user_id,
        vendor_org_id=actor.vendor_org_id,
    )


def merge_available_actions(
    actor: RequestContext,
    row: Mapping[str, Any],
    workflow_actions: list[str],
) -> list[AvailableAction]:
    """Merge C-owned workflow actions with B-owned public API actions."""
    internal_status = TicketStatus(str(row["status_code"]))
    if internal_status is TicketStatus.CLOSED:
        return []

    actions = [AvailableAction(action) for action in workflow_actions]

    def add(action: AvailableAction) -> None:
        if action not in actions:
            actions.append(action)

    role = UserRole(actor.role)
    if role is UserRole.EXTERNAL_VENDOR:
        if row.get("vendor_request_status") == "ACTIVE":
            add(AvailableAction.UPLOAD_ATTACHMENT)
        return actions

    if not (role is UserRole.USER and internal_status is TicketStatus.PENDING_USER):
        add(AvailableAction.COMMENT)
    add(AvailableAction.UPLOAD_ATTACHMENT)

    if role is UserRole.USER and internal_status is TicketStatus.UNASSIGNED:
        add(AvailableAction.EDIT)
    elif role is UserRole.SERVICE_DESK_MANAGER:
        add(AvailableAction.EDIT)
    return actions


def assemble_ticket_summary(
    database: Session,
    *,
    actor: RequestContext,
    row: Mapping[str, Any],
) -> TicketSummary:
    """Build a summary from a role-scoped ticket repository row."""
    workflow = WorkflowReadModel(database).get_role_view(
        ticket_id=int(row["ticket_id"]), actor=_actor_context(actor)
    )
    return TicketSummary(
        ticket_id=int(row["ticket_id"]),
        title=str(row["title"]),
        category=Category(str(row["category_code"])),
        priority=Priority(str(row["priority_code"])),
        status=TicketStatus(workflow["status"]),
        display_status=str(workflow["display_status"]),
        assignee=workflow["assignee"],
        sla=workflow["sla"],
        available_actions=merge_available_actions(
            actor, row, workflow["available_actions"]
        ),
        created_at=as_utc(row["created_at"]),
        updated_at=as_utc(row["updated_at"]),
    )


def assemble_ticket_detail(
    database: Session,
    *,
    actor: RequestContext,
    ticket_id: int,
) -> TicketDetail | None:
    """Return the public TicketDetail without committing or mutating state."""
    row = TicketRepository(database).detail(actor, ticket_id)
    if row is None:
        return None

    workflow = WorkflowReadModel(database).get_role_view(
        ticket_id=ticket_id, actor=_actor_context(actor)
    )
    role = UserRole(actor.role)
    summary = TicketSummary(
        ticket_id=ticket_id,
        title=str(row["title"]),
        category=Category(str(row["category_code"])),
        priority=Priority(str(row["priority_code"])),
        status=TicketStatus(workflow["status"]),
        display_status=str(workflow["display_status"]),
        assignee=workflow["assignee"],
        sla=workflow["sla"],
        available_actions=merge_available_actions(
            actor, row, workflow["available_actions"]
        ),
        created_at=as_utc(row["created_at"]),
        updated_at=as_utc(row["updated_at"]),
    )
    return TicketDetail(
        **summary.model_dump(),
        description=(
            None
            if role is UserRole.EXTERNAL_VENDOR
            else str(row["description"])
        ),
        requester=workflow["requester"],
        pending_user=workflow["pending_user"],
        resolution=workflow["resolution"],
        closure=workflow["closure"],
        vendor_request=(
            workflow["vendor_request"]
            if role
            in {
                UserRole.ENGINEER_TIER2,
                UserRole.SERVICE_DESK_MANAGER,
                UserRole.EXTERNAL_VENDOR,
            }
            else None
        ),
    )
