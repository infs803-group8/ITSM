"""ORM mappings for users, user skills and vendor organisations."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class VendorOrganisation(Base):
    __tablename__ = "vendor_organisations"

    vendor_org_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
        server_onupdate=text("CURRENT_TIMESTAMP(6)"),
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index(
            "idx_users_engineer_candidates",
            "role_code",
            "is_active",
            "is_available",
            "last_assigned_at",
            "user_id",
        ),
        Index("idx_users_vendor_scope", "vendor_org_id", "is_active", "user_id"),
    )

    user_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role_code: Mapped[str] = mapped_column(String(32), nullable=False)
    is_available: Mapped[bool | None] = mapped_column(nullable=True)
    vendor_org_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("vendor_organisations.vendor_org_id"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default=text("1"))
    last_assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
        server_onupdate=text("CURRENT_TIMESTAMP(6)"),
    )


class UserSkill(Base):
    __tablename__ = "user_skills"

    user_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True), ForeignKey("users.user_id"), primary_key=True
    )
    category_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)")
    )
