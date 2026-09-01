"""Read-only workflow projection contract."""

from typing import Any, Protocol


class WorkflowReadModel(Protocol):
    def get_ticket_workflow(self, *, ticket_id: int) -> dict[str, Any]: ...
