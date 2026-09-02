"""Attachment-specific ticket scope and visibility decisions."""

from dataclasses import dataclass

from app.common.request_context import RequestContext
from app.core.enums import AttachmentVisibility, UserRole
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


class AttachmentAccessPolicy:
    """Apply role, assignment, visibility and vendor-scope rules."""

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

    @classmethod
    def ensure_ticket_write(
        cls,
        record: TicketAccessRecord | None,
        actor: RequestContext,
        visibility: AttachmentVisibility,
    ) -> tuple[int | None, int | None]:
        cls.ensure_ticket_read(record, actor)
        assert record is not None
        if record.status_code == "CLOSED":
            raise ApplicationError(
                "TICKET_CLOSED",
                "Attachments cannot be added to a closed ticket.",
                409,
            )

        allowed_visibility = {
            UserRole.USER: {AttachmentVisibility.USER_VISIBLE},
            UserRole.ENGINEER_TIER1: {
                AttachmentVisibility.USER_VISIBLE,
                AttachmentVisibility.INTERNAL_ONLY,
            },
            UserRole.ENGINEER_TIER2: set(AttachmentVisibility),
            UserRole.EXTERNAL_VENDOR: {AttachmentVisibility.VENDOR_SHARED},
            UserRole.SERVICE_DESK_MANAGER: set(AttachmentVisibility),
        }.get(actor.role, set())
        if visibility not in allowed_visibility:
            raise ApplicationError(
                "DATA_SCOPE_DENIED",
                "The requested attachment visibility is not available to this role.",
                403,
            )

        if visibility == AttachmentVisibility.VENDOR_SHARED:
            if (
                record.active_vendor_request_id is None
                or record.active_vendor_org_id is None
                or (
                    actor.role == UserRole.EXTERNAL_VENDOR
                    and record.active_vendor_org_id != actor.vendor_org_id
                )
            ):
                raise ApplicationError(
                    "NO_ACTIVE_VENDOR_REQUEST",
                    "An active vendor request is required for vendor-shared attachments.",
                    409,
                )
            return record.active_vendor_request_id, record.active_vendor_org_id
        return None, None

    @staticmethod
    def readable_visibilities(actor: RequestContext) -> set[AttachmentVisibility]:
        return {
            UserRole.USER: {AttachmentVisibility.USER_VISIBLE},
            UserRole.ENGINEER_TIER1: {
                AttachmentVisibility.USER_VISIBLE,
                AttachmentVisibility.INTERNAL_ONLY,
            },
            UserRole.ENGINEER_TIER2: set(AttachmentVisibility),
            UserRole.EXTERNAL_VENDOR: {AttachmentVisibility.VENDOR_SHARED},
            UserRole.SERVICE_DESK_MANAGER: set(AttachmentVisibility),
        }.get(actor.role, set())

    @classmethod
    def resolve_visibility_filter(
        cls,
        actor: RequestContext,
        requested: AttachmentVisibility | None,
    ) -> set[AttachmentVisibility]:
        allowed = cls.readable_visibilities(actor)
        if not allowed:
            raise resource_not_found()
        if requested is not None and requested not in allowed:
            raise ApplicationError(
                "DATA_SCOPE_DENIED",
                "The requested attachment visibility is not available to this role.",
                403,
            )
        return {requested} if requested is not None else allowed
