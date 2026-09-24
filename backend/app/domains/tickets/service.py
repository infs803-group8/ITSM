"""Ticket core orchestration for API-15 through API-18."""

from sqlalchemy.orm import Session

from app.common.pagination import PaginationMeta
from app.common.request_context import RequestContext
from app.core.clock import utc_now
from app.core.enums import (
    Category,
    EventScope,
    EventType,
    Priority,
    SlaStatus,
    TicketStatus,
    UserRole,
)
from app.core.errors import ApplicationError
from app.domains.audit.service import AuditService
from app.domains.tickets.detail_assembler import (
    assemble_ticket_detail,
    assemble_ticket_summary,
)
from app.domains.tickets.repository import TicketRepository
from app.domains.tickets.schema import (
    TicketCreateRequest,
    TicketDetailResponse,
    TicketListResponse,
    TicketUpdateRequest,
)
from app.domains.workflow.ticket_creation import initialize_ticket_workflow


class TicketService:
    def __init__(self, database: Session) -> None:
        self.database = database
        self.repository = TicketRepository(database)
        self.audit = AuditService(database)

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
            detail = assemble_ticket_detail(
                self.database, actor=actor, ticket_id=ticket.ticket_id
            )
            assert detail is not None
            return TicketDetailResponse(data=detail)
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
        if actor.role == UserRole.EXTERNAL_VENDOR:
            if sla_status is not None:
                raise ApplicationError(
                    "DATA_SCOPE_DENIED",
                    "The SLA filter is not available to external vendors.",
                    403,
                )
            visible_vendor_statuses = {
                TicketStatus.IN_PROGRESS,
                TicketStatus.PENDING_VENDOR,
                TicketStatus.CLOSED,
            }
            if status is not None and status not in visible_vendor_statuses:
                raise ApplicationError(
                    "DATA_SCOPE_DENIED",
                    "The requested status is not visible to external vendors.",
                    403,
                )
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
            data=[assemble_ticket_summary(self.database, actor=actor, row=row) for row in rows],
            meta=PaginationMeta.from_total(page=page, page_size=page_size, total=total),
        )

    def get(self, actor: RequestContext, ticket_id: int) -> TicketDetailResponse:
        detail = assemble_ticket_detail(self.database, actor=actor, ticket_id=ticket_id)
        if detail is None:
            raise ApplicationError("RESOURCE_NOT_FOUND", "Ticket not found.", 404)
        return TicketDetailResponse(data=detail)

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
            detail = assemble_ticket_detail(self.database, actor=actor, ticket_id=ticket_id)
            assert detail is not None
            return TicketDetailResponse(data=detail)
        except Exception:
            if self.database.in_transaction():
                self.database.rollback()
            raise
