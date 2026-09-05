"""Role/scope-aware audit event operations (API-32) plus the internal
``append_event`` helper other domains call to write their own history.
"""

import json
from typing import Any

from sqlalchemy.orm import Session

from app.common.pagination import PaginationMeta
from app.common.request_context import RequestContext
from app.core.clock import as_utc
from app.core.enums import EventScope, EventType, UserRole
from app.domains.audit.access_policy import AuditAccessPolicy
from app.domains.audit.repository import AuditRepository
from app.domains.audit.schema import ActorSummary, EventListResponse
from app.domains.audit.schema import TicketEvent as TicketEventSchema


class AuditService:
    def __init__(self, database: Session) -> None:
        self.database = database
        self.repository = AuditRepository(database)

    def append_event(
        self,
        *,
        ticket_id: int,
        event_type: EventType,
        scope: EventScope,
        actor_id: int | None,
        vendor_org_id: int | None = None,
        cycle_no: int | None = None,
        comment_id: int | None = None,
        attachment_id: str | None = None,
        vendor_request_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Append one audit event within the caller's own transaction.

        Every other C-owned (and eventually A/B) service that changes a
        ticket calls this instead of writing to ``ticket_events`` itself,
        so the event/comment/attachment CHECK constraints and the
        cycle-guard uniqueness rule stay centrally maintained in one
        place. This method never commits.
        """
        self.repository.append(
            ticket_id=ticket_id,
            event_type=event_type.value,
            scope=scope.value,
            actor_id=actor_id,
            vendor_org_id=vendor_org_id,
            cycle_no=cycle_no,
            comment_id=comment_id,
            attachment_id=attachment_id,
            vendor_request_id=vendor_request_id,
            metadata=metadata,
        )

    @staticmethod
    def _actor(row: Any) -> ActorSummary | None:
        if row["actor_id"] is None:
            return None
        return ActorSummary(
            user_id=int(row["actor_id"]),
            display_name=str(row["actor_display_name"]),
            role=UserRole(str(row["actor_role"])),
        )

    @staticmethod
    def _metadata(row: Any) -> dict[str, Any]:
        raw = row["metadata"]
        if raw is None:
            return {}
        if isinstance(raw, str):
            return json.loads(raw)
        return dict(raw)

    def list_events(
        self,
        ticket_id: int,
        actor: RequestContext,
        *,
        event_type: EventType | None,
        scope: EventScope | None,
        page: int,
        page_size: int,
    ) -> EventListResponse:
        access_record = self.repository.get_ticket_access(ticket_id, actor)
        AuditAccessPolicy.ensure_ticket_read(access_record, actor)
        allowed_scopes = AuditAccessPolicy.resolve_scope_filter(actor, scope)
        vendor_org_id = (
            actor.vendor_org_id if actor.role == UserRole.EXTERNAL_VENDOR else None
        )

        rows, total = self.repository.list_events(
            ticket_id=ticket_id,
            allowed_scopes=[value.value for value in allowed_scopes],
            vendor_org_id=vendor_org_id,
            event_type=event_type.value if event_type is not None else None,
            scope=scope.value if scope is not None else None,
            page=page,
            page_size=page_size,
        )
        data = [
            TicketEventSchema(
                event_id=int(row["event_id"]),
                ticket_id=int(row["ticket_id"]),
                event_type=EventType(str(row["event_type"])),
                scope=EventScope(str(row["scope"])),
                actor=self._actor(row),
                cycle_no=int(row["cycle_no"]) if row["cycle_no"] is not None else None,
                occurred_at=as_utc(row["occurred_at"]),
                metadata=self._metadata(row),
            )
            for row in rows
        ]
        pagination = PaginationMeta.from_total(page=page, page_size=page_size, total=total)
        return EventListResponse(data=data, meta=pagination)
