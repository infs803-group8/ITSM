"""Ticket core orchestration for API-15 through API-18."""

from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from app.common.pagination import PaginationMeta
from app.common.request_context import RequestContext
from app.core.clock import as_utc, utc_now
from app.core.enums import (
    AvailableAction,
    Category,
    EventScope,
    EventType,
    PendingUserReason,
    Priority,
    SlaStatus,
    TicketStatus,
    UserRole,
    VendorRequestStatus,
)
from app.core.errors import ApplicationError
from app.domains.audit.service import AuditService
from app.domains.reference_data.schema import VendorOrganisation
from app.domains.tickets.repository import TicketRepository
from app.domains.tickets.schema import (
    ClosureView,
    PendingUserView,
    RequesterSummary,
    ResolutionView,
    TicketCreateRequest,
    TicketDetail,
    TicketDetailResponse,
    TicketListResponse,
    TicketSummary,
    TicketUpdateRequest,
    VendorRequestView,
)
from app.domains.users.schema import AssigneeSummary
from app.domains.workflow.read_model import WorkflowReadModel
from app.domains.workflow.serializer import ActorContext
from app.domains.workflow.ticket_creation import initialize_ticket_workflow


class TicketService:
    def __init__(self, database: Session) -> None:
        self.database = database
        self.repository = TicketRepository(database)
        self.audit = AuditService(database)
        self.workflow = WorkflowReadModel(database)

    @staticmethod
    def _visible_status(actor: RequestContext, value: str) -> TicketStatus:
        if actor.role == UserRole.USER and value == TicketStatus.PENDING_VENDOR:
            return TicketStatus.IN_PROGRESS
        return TicketStatus(value)

    @classmethod
    def _display_status(cls, actor: RequestContext, value: str) -> str:
        return cls._visible_status(actor, value).value.replace("_", " ").title()

    @staticmethod
    def _assignee(row: Mapping[str, Any]) -> AssigneeSummary | None:
        if row["assignee_id"] is None:
            return None
        return AssigneeSummary(
            user_id=int(row["assignee_id"]),
            display_name=str(row["assignee_name"]),
            tier="TIER1"
            if row["assignee_role"] == UserRole.ENGINEER_TIER1
            else "TIER2",
            skills=[
                Category(item)
                for item in str(row["assignee_skills"] or "").split(",")
                if item
            ],
            is_available=bool(row["assignee_available"]),
            active_load=int(row["assignee_active_load"] or 0),
        )

    @staticmethod
    def _actor_context(actor: RequestContext) -> ActorContext:
        return ActorContext(
            role=UserRole(actor.role),
            user_id=actor.user_id,
            vendor_org_id=actor.vendor_org_id,
        )

    @staticmethod
    def _actions(
        actor: RequestContext,
        row: Mapping[str, Any],
        workflow_actions: list[str],
    ) -> list[AvailableAction]:
        internal_status = str(row["status_code"])
        if internal_status == TicketStatus.CLOSED:
            return []
        actions = [AvailableAction(action) for action in workflow_actions]
        if actor.role == UserRole.EXTERNAL_VENDOR:
            if (
                row["vendor_request_status"] == VendorRequestStatus.ACTIVE
                and AvailableAction.UPLOAD_ATTACHMENT not in actions
            ):
                actions.append(AvailableAction.UPLOAD_ATTACHMENT)
            return actions
        if not (actor.role == UserRole.USER and internal_status == TicketStatus.PENDING_USER):
            actions.append(AvailableAction.COMMENT)
        actions.append(AvailableAction.UPLOAD_ATTACHMENT)
        if actor.role == UserRole.USER:
            if internal_status == TicketStatus.UNASSIGNED:
                actions.append(AvailableAction.EDIT)
        elif actor.role == UserRole.SERVICE_DESK_MANAGER:
            actions.append(AvailableAction.EDIT)
        return actions

    def _summary(self, actor: RequestContext, row: Mapping[str, Any]) -> TicketSummary:
        workflow = self.workflow.get_role_view(
            ticket_id=int(row["ticket_id"]), actor=self._actor_context(actor)
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
            available_actions=self._actions(actor, row, workflow["available_actions"]),
            created_at=as_utc(row["created_at"]),
            updated_at=as_utc(row["updated_at"]),
        )

    def _detail(self, actor: RequestContext, row: Mapping[str, Any]) -> TicketDetail:
        summary = self._summary(actor, row)
        vendor = None
        if row["vendor_request_id"] is not None and actor.role in {
            UserRole.ENGINEER_TIER2,
            UserRole.SERVICE_DESK_MANAGER,
            UserRole.EXTERNAL_VENDOR,
        }:
            vendor = VendorRequestView(
                vendor_request_id=int(row["vendor_request_id"]),
                vendor_org=VendorOrganisation(
                    vendor_org_id=int(row["request_vendor_org_id"]),
                    name=str(row["vendor_org_name"]),
                    is_active=bool(row["vendor_org_active"]),
                ),
                status=VendorRequestStatus(str(row["vendor_request_status"])),
                vendor_message=str(row["vendor_message"]),
                created_at=as_utc(row["vendor_request_created_at"]),
                responded_at=as_utc(row["responded_at"]) if row["responded_at"] else None,
            )
        pending = (
            PendingUserView(
                reason=PendingUserReason(str(row["pending_user_reason"])),
                deadline=as_utc(row["pending_user_deadline"]),
            )
            if row["pending_user_reason"] and actor.role != UserRole.EXTERNAL_VENDOR
            else None
        )
        resolution = (
            ResolutionView(
                summary=str(row["resolution_summary"]),
                type=row["resolution_type"],
                resolved_at=as_utc(row["resolved_at"]) if row["resolved_at"] else None,
                auto_close_at=as_utc(row["auto_close_at"]) if row["auto_close_at"] else None,
            )
            if row["resolution_summary"] and actor.role != UserRole.EXTERNAL_VENDOR
            else None
        )
        closure = (
            ClosureView(type=str(row["closure_type"]), closed_at=as_utc(row["closed_at"]))
            if row["closure_type"] and actor.role != UserRole.EXTERNAL_VENDOR
            else None
        )
        return TicketDetail(
            **summary.model_dump(),
            description=str(row["description"])
            if actor.role != UserRole.EXTERNAL_VENDOR
            else None,
            requester=RequesterSummary(
                user_id=int(row["requester_id"]), display_name=str(row["requester_name"])
            )
            if actor.role != UserRole.EXTERNAL_VENDOR
            else None,
            pending_user=pending,
            resolution=resolution,
            closure=closure,
            vendor_request=vendor,
        )

    def create(self, actor: RequestContext, request: TicketCreateRequest) -> TicketDetailResponse:
        if actor.role != UserRole.USER:
            raise ApplicationError("DATA_SCOPE_DENIED", "Only requesters may create tickets.", 403)
        now = utc_now()
        try:
            ticket = self.repository.create(
                requester_id=actor.user_id,
                title=request.title,
                description=request.description,
                category=request.category.value,
                priority=request.priority.value,
            )
            self.audit.append_event(
                ticket_id=ticket.ticket_id,
                event_type=EventType.TICKET_CREATED,
                scope=EventScope.USER_VISIBLE,
                actor_id=actor.user_id,
                metadata={},
            )
            initialize_ticket_workflow(
                self.database,
                ticket_id=ticket.ticket_id,
                category_code=request.category.value,
                now=now,
            )
            self.database.commit()
            row = self.repository.detail(actor, ticket.ticket_id)
            assert row is not None
            return TicketDetailResponse(data=self._detail(actor, row))
        except Exception:
            if self.database.in_transaction():
                self.database.rollback()
            raise

    def list(
        self,
        actor: RequestContext,
        *,
        page: int,
        page_size: int,
        status: TicketStatus | None,
        category: Category | None,
        priority: Priority | None,
        sla_status: SlaStatus | None,
        assignee_id: int | None,
        search: str | None,
        sort_by: str,
        sort_order: str,
    ) -> TicketListResponse:
        if assignee_id is not None and actor.role != UserRole.SERVICE_DESK_MANAGER:
            if actor.role not in {UserRole.ENGINEER_TIER1, UserRole.ENGINEER_TIER2} or (
                assignee_id != actor.user_id
            ):
                raise ApplicationError(
                    "DATA_SCOPE_DENIED", "The assignee filter is outside your data scope.", 403
                )
        internal_statuses = [status.value] if status is not None else None
        if actor.role == UserRole.USER and status == TicketStatus.PENDING_VENDOR:
            raise ApplicationError(
                "DATA_SCOPE_DENIED", "The requested status is not visible.", 403
            )
        if actor.role == UserRole.USER and status == TicketStatus.IN_PROGRESS:
            internal_statuses = [
                TicketStatus.IN_PROGRESS.value,
                TicketStatus.PENDING_VENDOR.value,
            ]
        rows, total = self.repository.list(
            actor,
            page=page,
            page_size=page_size,
            statuses=internal_statuses,
            category=category.value if category else None,
            priority=priority.value if priority else None,
            sla_status=sla_status.value if sla_status else None,
            assignee_id=assignee_id,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        return TicketListResponse(
            data=[self._summary(actor, row) for row in rows],
            meta=PaginationMeta.from_total(page=page, page_size=page_size, total=total),
        )

    def get(self, actor: RequestContext, ticket_id: int) -> TicketDetailResponse:
        row = self.repository.detail(actor, ticket_id)
        if row is None:
            raise ApplicationError("RESOURCE_NOT_FOUND", "Ticket not found.", 404)
        return TicketDetailResponse(data=self._detail(actor, row))

    def update(
        self, actor: RequestContext, ticket_id: int, request: TicketUpdateRequest
    ) -> TicketDetailResponse:
        try:
            ticket = self.repository.get_model(ticket_id, for_update=True)
            if ticket is None or not self.repository.visible(actor, ticket_id):
                raise ApplicationError("RESOURCE_NOT_FOUND", "Ticket not found.", 404)
            if ticket.status_code == TicketStatus.CLOSED:
                raise ApplicationError("TICKET_CLOSED", "Closed tickets are read-only.", 409)
            if actor.role == UserRole.USER:
                if ticket.requester_id != actor.user_id:
                    raise ApplicationError("RESOURCE_NOT_FOUND", "Ticket not found.", 404)
                if ticket.status_code != TicketStatus.UNASSIGNED:
                    raise ApplicationError(
                        "INVALID_STATUS_TRANSITION",
                        "A requester may edit only an unassigned ticket.",
                        409,
                    )
            elif actor.role != UserRole.SERVICE_DESK_MANAGER:
                raise ApplicationError("DATA_SCOPE_DENIED", "Ticket editing is not permitted.", 403)
            for field, column in (
                ("title", "title"),
                ("description", "description"),
                ("category", "category_code"),
                ("priority", "priority_code"),
            ):
                if field in request.model_fields_set:
                    value = getattr(request, field)
                    if hasattr(value, "value"):
                        value = value.value
                    setattr(ticket, column, value)
            self.repository.flush()
            self.database.commit()
            row = self.repository.detail(actor, ticket_id)
            assert row is not None
            return TicketDetailResponse(data=self._detail(actor, row))
        except Exception:
            if self.database.in_transaction():
                self.database.rollback()
            raise
