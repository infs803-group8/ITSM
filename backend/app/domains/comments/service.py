"""Ordinary comment rules for API-19 and API-20."""

from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from app.common.pagination import PaginationMeta
from app.common.request_context import RequestContext
from app.core.clock import as_utc
from app.core.enums import (
    CommentVisibility,
    PendingUserReason,
    TicketStatus,
    UserRole,
)
from app.core.errors import ApplicationError
from app.domains.comments.repository import CommentRepository
from app.domains.comments.schema import (
    ActorSummary,
    CommentCreateRequest,
    CommentListResponse,
    CommentResponse,
    CommentView,
)
from app.domains.tickets.repository import TicketRepository


class CommentService:
    def __init__(self, database: Session) -> None:
        self.database = database
        self.repository = CommentRepository(database)
        self.tickets = TicketRepository(database)

    @staticmethod
    def _view(row: Mapping[str, Any]) -> CommentView:
        return CommentView(
            comment_id=int(row["comment_id"]),
            ticket_id=int(row["ticket_id"]),
            author=ActorSummary(
                user_id=int(row["author_id"]),
                display_name=str(row["author_name"]),
                role=UserRole(str(row["author_role"])),
            ),
            message=str(row["message"]),
            visibility=CommentVisibility(str(row["visibility"])),
            created_at=as_utc(row["created_at"]),
        )

    def _authorise_read(self, actor: RequestContext, ticket_id: int) -> None:
        if actor.role == UserRole.EXTERNAL_VENDOR:
            raise ApplicationError(
                "DATA_SCOPE_DENIED", "Vendors do not use the ordinary comment API.", 403
            )
        if not self.tickets.visible(actor, ticket_id):
            raise ApplicationError("RESOURCE_NOT_FOUND", "Ticket not found.", 404)

    def list(
        self,
        actor: RequestContext,
        ticket_id: int,
        *,
        page: int,
        page_size: int,
        visibility: CommentVisibility | None,
    ) -> CommentListResponse:
        self._authorise_read(actor, ticket_id)
        if actor.role == UserRole.USER and visibility == CommentVisibility.INTERNAL_ONLY:
            raise ApplicationError(
                "DATA_SCOPE_DENIED", "Internal comments are not visible to requesters.", 403
            )
        rows, total = self.repository.list(
            ticket_id=ticket_id,
            page=page,
            page_size=page_size,
            visibility=visibility.value if visibility else None,
            user_visible_only=actor.role == UserRole.USER,
        )
        return CommentListResponse(
            data=[self._view(row) for row in rows],
            meta=PaginationMeta.from_total(page=page, page_size=page_size, total=total),
        )

    def create(
        self, actor: RequestContext, ticket_id: int, request: CommentCreateRequest
    ) -> CommentResponse:
        try:
            ticket = self.tickets.get_model(ticket_id, for_update=True)
            if ticket is None or not self.tickets.visible(actor, ticket_id):
                raise ApplicationError("RESOURCE_NOT_FOUND", "Ticket not found.", 404)
            if ticket.status_code == TicketStatus.CLOSED:
                raise ApplicationError("TICKET_CLOSED", "Closed tickets are read-only.", 409)
            if actor.role == UserRole.EXTERNAL_VENDOR:
                if ticket.status_code == TicketStatus.PENDING_VENDOR:
                    raise ApplicationError(
                        "USE_VENDOR_RESPONSE_ACTION",
                        "Use the vendor response action for this ticket.",
                        409,
                    )
                raise ApplicationError(
                    "DATA_SCOPE_DENIED", "Vendors do not use the ordinary comment API.", 403
                )
            if actor.role == UserRole.USER and ticket.status_code == TicketStatus.PENDING_USER:
                code = (
                    "USE_CONFIRM_OR_RESUME_ACTION"
                    if ticket.pending_user_reason == PendingUserReason.RESOLUTION_CONFIRMATION
                    else "USE_RESUME_ACTION"
                )
                raise ApplicationError(
                    code, "Use the ticket's formal workflow action instead of a comment.", 409
                )
            if (
                request.visibility == CommentVisibility.INTERNAL_ONLY
                and actor.role
                not in {
                    UserRole.ENGINEER_TIER1,
                    UserRole.ENGINEER_TIER2,
                    UserRole.SERVICE_DESK_MANAGER,
                }
            ):
                raise ApplicationError(
                    "DATA_SCOPE_DENIED", "Internal comments require staff access.", 403
                )
            comment = self.repository.create(
                ticket_id=ticket_id,
                author_id=actor.user_id,
                message=request.message,
                visibility=request.visibility.value,
            )
            self.repository.add_event(comment)
            self.database.commit()
            return CommentResponse(data=self._view(self.repository.view(comment.comment_id)))
        except Exception:
            if self.database.in_transaction():
                self.database.rollback()
            raise
