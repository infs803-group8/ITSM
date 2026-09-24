"""SQLAlchemy mapping for the canonical comments table."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Comment(Base):
    __tablename__ = "comments"

    comment_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True)
    ticket_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("tickets.ticket_id"), nullable=False
    )
    author_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.user_id"), nullable=False
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[str] = mapped_column(String(32), nullable=False)
    comment_type: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'ORDINARY'")
    )
    workflow_action: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)")
    )
