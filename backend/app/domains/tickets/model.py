"""SQLAlchemy mapping for the canonical tickets table."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.mysql import BIGINT, INTEGER
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Ticket(Base):
    __tablename__ = "tickets"

    ticket_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True)
    requester_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.user_id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category_code: Mapped[str] = mapped_column(String(32), nullable=False)
    priority_code: Mapped[str] = mapped_column(String(16), nullable=False)
    status_code: Mapped[str] = mapped_column(String(32), nullable=False, default="NEW")
    assignee_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.user_id")
    )
    last_resolved_assignee_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.user_id")
    )
    sla_cycle_no: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), nullable=False, default=1
    )
    sla_status_code: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ON_TRACK"
    )
    sla_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    sla_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    pending_user_reason: Mapped[str | None] = mapped_column(String(32))
    pending_user_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    resolution_summary: Mapped[str | None] = mapped_column(Text)
    resolution_type: Mapped[str | None] = mapped_column(String(64))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    auto_close_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    closure_type: Mapped[str | None] = mapped_column(String(32))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
        server_onupdate=text("CURRENT_TIMESTAMP(6)"),
    )
