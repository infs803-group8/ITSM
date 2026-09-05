"""SQLAlchemy mapping for the append-only ``ticket_events`` audit table.

Cross-domain foreign keys (ticket_id, actor_id, vendor_org_id, comment_id,
attachment_id, vendor_request_id) are enforced by
``backend/database/schema.sql`` rather than repeated here, matching the
convention in ``app.domains.attachments.model`` -- this keeps the mapper
usable before Member B's User/Ticket ORM models and Member C's own
vendor_workflow models exist.

The three ``cycle_guard_*`` generated (STORED) columns and the
``uq_ticket_events_cycle_guard`` unique key that makes SLA-cycle event
writes idempotent across job re-runs are DB-only mechanics computed by
MySQL itself; they are intentionally not mapped here, the same way the
attachment mapper omits FK-enforcement mechanics that live only in SQL.
The two append-only triggers (``trg_ticket_events_no_update``,
``trg_ticket_events_no_delete``) are why this module never defines an
``update``/``delete`` helper -- only ``INSERT`` is a valid operation on
this table.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, text
from sqlalchemy.dialects.mysql import BIGINT, CHAR, INTEGER, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TicketEvent(Base):
    __tablename__ = "ticket_events"
    __table_args__ = (
        Index("uq_ticket_events_comment", "comment_id", unique=True),
        Index("uq_ticket_events_attachment", "attachment_id", unique=True),
        Index(
            "idx_ticket_events_ticket_scope_time",
            "ticket_id",
            "scope",
            "occurred_at",
            "event_id",
        ),
        Index("idx_ticket_events_type_time", "event_type", "occurred_at", "event_id"),
        Index(
            "idx_ticket_events_vendor_scope",
            "vendor_org_id",
            "ticket_id",
            "occurred_at",
            "event_id",
        ),
        Index("idx_ticket_events_vendor_request", "vendor_request_id", "occurred_at"),
    )

    event_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), primary_key=True, autoincrement=True
    )
    ticket_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[int | None] = mapped_column(BIGINT(unsigned=True), nullable=True)
    vendor_org_id: Mapped[int | None] = mapped_column(BIGINT(unsigned=True), nullable=True)
    cycle_no: Mapped[int | None] = mapped_column(INTEGER(unsigned=True), nullable=True)
    comment_id: Mapped[int | None] = mapped_column(BIGINT(unsigned=True), nullable=True)
    attachment_id: Mapped[str | None] = mapped_column(
        CHAR(36, charset="ascii", collation="ascii_bin"), nullable=True
    )
    vendor_request_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True), nullable=True
    )
    # Mapped as ``metadata_json`` because ``metadata`` is reserved on the
    # SQLAlchemy Declarative Base; the physical column name is unchanged.
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, nullable=False, server_default=text("(JSON_OBJECT())")
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
    )
