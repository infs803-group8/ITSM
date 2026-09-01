"""Initial ticket assignment contract."""

from typing import Protocol


class InitialAssignmentService(Protocol):
    def assign_new_ticket(self, *, ticket_id: int, category_id: int) -> int | None: ...
