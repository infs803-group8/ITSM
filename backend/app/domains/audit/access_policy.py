"""Audit-specific ticket scope and event-scope visibility decisions.

Mirrors ``app.domains.attachments.access_policy`` (same duck-typed
``TicketAccessRecord`` shape, same "hidden ticket -> 404" rule) since both
domains gate access to the same ``tickets`` row and neither owns a
finished Ticket ORM model yet. See docs/project-management/decision-log.md
Q11 (Audit Role x EventScope matrix, pending A/B/D confirmation -- not
Q02, which covers TicketDetail field redaction for Vendor responses)
for why EventScope is treated the same way AttachmentVisibility is:
USER_VISIBLE/INTERNAL_ONLY are readable by an increasing set of internal
roles, and the vendor-facing scope is additionally restricted to the
actor's own vendor organisation at the query layer.
"""

from dataclasses import dataclass

from app.common.request_context import RequestContext
from app.core.enums import EventScope, UserRole
from app.core.errors import ApplicationError


@dataclass(frozen=True)
class TicketAccessRecord:
    ticket_id: int
    requester_id: int
    assignee_id: int | None
    status_code: str
    active_vendor_request_id: int | None
    active_vendor_org_id: int | None
    actor_has_vendor_history: bool = False


def resource_not_found() -> ApplicationError:
    return ApplicationError(
        "RESOURCE_NOT_FOUND",
        "The requested resource was not found.",
        404,
    )


class AuditAccessPolicy:
    """Apply role, assignment and vendor-history visibility rules."""

    @staticmethod
    def ensure_ticket_read(record: TicketAccessRecord | None, actor: RequestContext) -> None:
        if record is None:
            raise resource_not_found()
        allowed = {
            UserRole.USER: record.requester_id == actor.user_id,
            UserRole.ENGINEER_TIER1: record.assignee_id == actor.user_id,
            UserRole.ENGINEER_TIER2: record.assignee_id == actor.user_id,
            UserRole.EXTERNAL_VENDOR: (
                actor.vendor_org_id is not None and record.actor_has_vendor_history
            ),
            UserRole.SERVICE_DESK_MANAGER: True,
        }.get(actor.role, False)
        if not allowed:
            raise resource_not_found()

    @staticmethod
    def readable_scopes(actor: RequestContext) -> set[EventScope]:
        return {
            UserRole.USER: {EventScope.USER_VISIBLE},
            UserRole.ENGINEER_TIER1: {EventScope.USER_VISIBLE, EventScope.INTERNAL_ONLY},
            UserRole.ENGINEER_TIER2: set(EventScope),
            UserRole.EXTERNAL_VENDOR: {EventScope.VENDOR_SCOPE},
            UserRole.SERVICE_DESK_MANAGER: set(EventScope),
        }.get(actor.role, set())

    @classmethod
    def resolve_scope_filter(
        cls,
        actor: RequestContext,
        requested: EventScope | None,
    ) -> set[EventScope]:
        allowed = cls.readable_scopes(actor)
        if not allowed:
            raise resource_not_found()
        if requested is not None and requested not in allowed:
            raise ApplicationError(
                "DATA_SCOPE_DENIED",
                "The requested event scope is not available to this role.",
                403,
            )
        return {requested} if requested is not None else allowed
