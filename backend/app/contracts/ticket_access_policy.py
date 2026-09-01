"""Cross-domain ticket visibility contract."""

from typing import Protocol


class TicketAccessPolicy(Protocol):
    def can_view(self, *, user_id: int, role: str, ticket_id: int) -> bool: ...
    def can_modify(self, *, user_id: int, role: str, ticket_id: int) -> bool: ...
