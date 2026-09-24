"""Canonical role-aware ticket access policy used by other domains."""

from sqlalchemy.orm import Session

from app.common.request_context import RequestContext
from app.core.enums import UserRole
from app.domains.tickets.repository import TicketRepository


class TicketAccessPolicy:
    def __init__(self, database: Session) -> None:
        self.repository = TicketRepository(database)

    def can_view(self, *, user_id: int, role: str, ticket_id: int) -> bool:
        return self.repository.visible(RequestContext(user_id=user_id, role=role), ticket_id)

    def can_modify(self, *, user_id: int, role: str, ticket_id: int) -> bool:
        actor = RequestContext(user_id=user_id, role=role)
        if not self.repository.visible(actor, ticket_id):
            return False
        ticket = self.repository.get_model(ticket_id)
        return bool(
            ticket
            and ticket.status_code != "CLOSED"
            and (
                role == UserRole.SERVICE_DESK_MANAGER
                or (
                    role == UserRole.USER
                    and ticket.requester_id == user_id
                    and ticket.status_code == "UNASSIGNED"
                )
            )
        )
