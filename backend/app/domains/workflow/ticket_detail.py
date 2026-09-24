"""Assemble the public ``TicketDetail`` shape for ``TicketActionResponse``
(C024 onward).

Member B's ``app.domains.tickets.*`` is still an empty stub at the time
this module was written, and every write-path handler from C024 on
(``POST /tickets/{id}/assign``, ``/start``, ``/resolve``, ...) must return
a complete ``TicketActionResponse`` containing a full ``TicketDetail`` --
not just the workflow slice ``WorkflowReadModel`` already covers. Rather
than leaving every one of those endpoints half-blocked on B, this module
reads B's core ticket fields (title, description, category, priority,
created_at, updated_at) directly via raw SQL against the physical
``tickets`` table -- the same pattern this whole codebase already uses
for every other read of a table Member B hasn't built an ORM model for
yet (``dashboard/repository.py``, ``workflow/repository.py``, and so on).
It only reads those columns, never writes them, so there is no conflict
with B's own eventual work; once B has a real ticket-detail assembler,
C024-C034's routers should be repointed at it instead of this module.

Known, explicitly flagged gap: the ``EDIT``/``COMMENT``/``UPLOAD_ATTACHMENT``
members of the public ``AvailableAction`` enum belong to B's tickets
domain and the comments/attachments domains respectively (see
``workflow/serializer.py``'s own docstring), none of which have
implemented their own eligibility checks yet. Until they do, this module
adds ``COMMENT``/``UPLOAD_ATTACHMENT`` whenever the ticket is not
``CLOSED`` (matching every open-ticket example in docs/api/openapi.yaml)
and never adds ``EDIT`` (no sampled example ever includes it, and its
actual eligibility rule -- e.g. "only the requester, only before
assignment" -- is not this domain's call to make up).
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.clock import as_utc
from app.domains.workflow.read_model import WorkflowReadModel
from app.domains.workflow.serializer import ActorContext


def _get_ticket_core(database: Session, ticket_id: int) -> dict[str, Any] | None:
    row = (
        database.execute(
            text(
                """
                SELECT ticket_id, title, description, category_code, priority_code,
                       created_at, updated_at
                FROM tickets
                WHERE ticket_id = :ticket_id
                """
            ),
            {"ticket_id": ticket_id},
        )
        .mappings()
        .one_or_none()
    )
    return dict(row) if row is not None else None


def assemble_ticket_detail(
    database: Session, *, ticket_id: int, actor: ActorContext
) -> dict[str, Any] | None:
    """Returns ``None`` if the ticket does not exist -- callers translate
    that into the standard 404 ``RESOURCE_NOT_FOUND`` response themselves,
    same convention as ``WorkflowReadModel`` raising ``KeyError`` (this
    returns ``None`` instead purely because a missing core row and a
    missing workflow row can never disagree -- both read the same table).
    """
    core = _get_ticket_core(database, ticket_id)
    if core is None:
        return None
    workflow_view = WorkflowReadModel(database).get_role_view(ticket_id=ticket_id, actor=actor)
    available_actions = list(workflow_view["available_actions"])
    if workflow_view["status"] != "CLOSED":
        for action in ("COMMENT", "UPLOAD_ATTACHMENT"):
            if action not in available_actions:
                available_actions.append(action)
    return {
        "ticket_id": core["ticket_id"],
        "title": core["title"],
        "description": None if actor.role.value == "EXTERNAL_VENDOR" else core["description"],
        "category": core["category_code"],
        "priority": core["priority_code"],
        "status": workflow_view["status"],
        "display_status": workflow_view["display_status"],
        "requester": workflow_view["requester"],
        "assignee": workflow_view["assignee"],
        "sla": workflow_view["sla"],
        "pending_user": workflow_view["pending_user"],
        "resolution": workflow_view["resolution"],
        "closure": workflow_view["closure"],
        "vendor_request": workflow_view["vendor_request"],
        "available_actions": available_actions,
        "created_at": as_utc(core["created_at"]),
        "updated_at": as_utc(core["updated_at"]),
    }
