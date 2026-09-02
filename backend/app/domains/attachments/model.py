"""SQLAlchemy mappings for the two Member A attachment tables."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.mysql import BIGINT, CHAR, VARCHAR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AttachmentUpload(Base):
    __tablename__ = "attachment_uploads"
    __table_args__ = (
        Index("uq_attachment_uploads_object_key", "object_key", unique=True),
        Index("uq_attachment_uploads_attachment", "attachment_id", unique=True),
        Index("idx_attachment_uploads_ticket_creator", "ticket_id", "creator_id", "created_at"),
        Index("idx_attachment_uploads_cleanup", "status", "expires_at", "upload_id"),
        Index(
            "idx_attachment_uploads_vendor_scope",
            "vendor_org_id",
            "vendor_request_id",
            "status",
        ),
    )

    upload_id: Mapped[str] = mapped_column(
        CHAR(36, charset="ascii", collation="ascii_bin"), primary_key=True
    )
    ticket_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("tickets.ticket_id", name="fk_attachment_uploads_ticket"),
        nullable=False,
    )
    creator_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("users.user_id", name="fk_attachment_uploads_creator"),
        nullable=False,
    )
    object_key: Mapped[str] = mapped_column(
        VARCHAR(1024, charset="ascii", collation="ascii_bin"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    expected_content_type: Mapped[str] = mapped_column(
        VARCHAR(100, charset="ascii", collation="ascii_bin"), nullable=False
    )
    expected_size: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    visibility: Mapped[str] = mapped_column(String(32), nullable=False)
    vendor_request_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey(
            "vendor_requests.vendor_request_id",
            name="fk_attachment_uploads_vendor_request",
        ),
        nullable=True,
    )
    vendor_org_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey(
            "vendor_organisations.vendor_org_id",
            name="fk_attachment_uploads_vendor_org",
        ),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'PENDING'")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    aborted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    attachment_id: Mapped[str | None] = mapped_column(
        CHAR(36, charset="ascii", collation="ascii_bin"),
        ForeignKey("attachments.attachment_id", name="fk_attachment_uploads_attachment"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
        server_onupdate=text("CURRENT_TIMESTAMP(6)"),
    )


class Attachment(Base):
    __tablename__ = "attachments"
    __table_args__ = (
        Index("uq_attachments_upload", "upload_id", unique=True),
        Index("uq_attachments_object_key", "object_key", unique=True),
        Index(
            "idx_attachments_ticket_visibility_time",
            "ticket_id",
            "visibility",
            "created_at",
            "attachment_id",
        ),
        Index(
            "idx_attachments_vendor_scope",
            "vendor_org_id",
            "vendor_request_id",
            "ticket_id",
            "created_at",
        ),
    )

    attachment_id: Mapped[str] = mapped_column(
        CHAR(36, charset="ascii", collation="ascii_bin"), primary_key=True
    )
    upload_id: Mapped[str] = mapped_column(
        CHAR(36, charset="ascii", collation="ascii_bin"),
        ForeignKey("attachment_uploads.upload_id", name="fk_attachments_upload"),
        nullable=False,
    )
    ticket_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("tickets.ticket_id", name="fk_attachments_ticket"),
        nullable=False,
    )
    creator_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("users.user_id", name="fk_attachments_creator"),
        nullable=False,
    )
    object_key: Mapped[str] = mapped_column(
        VARCHAR(1024, charset="ascii", collation="ascii_bin"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    verified_content_type: Mapped[str] = mapped_column(
        VARCHAR(100, charset="ascii", collation="ascii_bin"), nullable=False
    )
    verified_size: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    visibility: Mapped[str] = mapped_column(String(32), nullable=False)
    vendor_request_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey(
            "vendor_requests.vendor_request_id", name="fk_attachments_vendor_request"
        ),
    )
    vendor_org_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey(
            "vendor_organisations.vendor_org_id", name="fk_attachments_vendor_org"
        ),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
    )
