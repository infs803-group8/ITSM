"""Read-only workflow projection contract.

Implemented by ``app.domains.workflow.read_model.WorkflowReadModel`` (C021).
That concrete class also exposes ``get_role_view(*, ticket_id, actor)`` for
role-serialized reads, in addition to this Protocol's actor-agnostic method.
"""

from typing import Any, Protocol


class WorkflowReadModel(Protocol):
    def get_ticket_workflow(self, *, ticket_id: int) -> dict[str, Any]: ...
