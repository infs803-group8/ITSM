"""Pydantic contract for API-32 (backend/contracts/openapi.yaml: /tickets/{id}/events).

Field shapes are copied 1:1 from the OpenAPI ``ActorSummary``,
``TicketEvent`` and ``EventListResponse`` schemas.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.common.pagination import PaginationMeta
from app.core.enums import EventScope, EventType, UserRole


class ActorSummary(BaseModel):
    user_id: int
    display_name: str
    role: UserRole


class TicketEvent(BaseModel):
    event_id: int
    ticket_id: int
    event_type: EventType
    scope: EventScope
    actor: ActorSummary | None
    cycle_no: int | None = Field(default=None, ge=1)
    occurred_at: datetime
    metadata: dict[str, Any]


class EventListResponse(BaseModel):
    data: list[TicketEvent]
    meta: PaginationMeta
