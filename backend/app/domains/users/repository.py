"""Persistence operations for profiles and the assignee directory."""

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.domains.users.model import User, VendorOrganisation


class UserRepository:
    def __init__(self, database: Session) -> None:
        self.database = database

    def get_active(self, user_id: int, *, for_update: bool = False) -> User | None:
        statement = select(User).where(User.user_id == user_id, User.is_active.is_(True))
        if for_update:
            statement = statement.with_for_update()
        return self.database.execute(statement).scalar_one_or_none()

    def get_vendor_organisation(self, vendor_org_id: int | None) -> VendorOrganisation | None:
        if vendor_org_id is None:
            return None
        return self.database.get(VendorOrganisation, vendor_org_id)

    def flush(self) -> None:
        self.database.flush()

    def list_assignees(
        self,
        *,
        page: int,
        page_size: int,
        tier: str | None,
        category: str | None,
        is_available: bool | None,
    ) -> tuple[Sequence[Mapping[str, Any]], int]:
        filters = ["u.role_code IN ('ENGINEER_TIER1', 'ENGINEER_TIER2')", "u.is_active = 1"]
        params: dict[str, Any] = {"limit": page_size, "offset": (page - 1) * page_size}
        if tier is not None:
            filters.append("u.role_code = :role")
            params["role"] = f"ENGINEER_{tier}"
        if category is not None:
            filters.append(
                "EXISTS (SELECT 1 FROM user_skills f WHERE f.user_id = u.user_id "
                "AND f.category_code = :category)"
            )
            params["category"] = category
        if is_available is not None:
            filters.append("u.is_available = :is_available")
            params["is_available"] = is_available
        where = " AND ".join(filters)
        total = int(
            self.database.execute(
                text(f"SELECT COUNT(*) FROM users u WHERE {where}"), params
            ).scalar_one()
        )
        rows = self.database.execute(
            text(
                f"""
                SELECT u.user_id, u.display_name, u.role_code, u.is_available,
                       COALESCE(skills.skill_codes, '') AS skill_codes,
                       COALESCE(loads.active_load, 0) AS active_load
                FROM users u
                LEFT JOIN (
                    SELECT user_id, GROUP_CONCAT(category_code ORDER BY category_code)
                      AS skill_codes
                    FROM user_skills GROUP BY user_id
                ) skills ON skills.user_id = u.user_id
                LEFT JOIN (
                    SELECT assignee_id, COUNT(*) AS active_load FROM tickets
                    WHERE status_code IN ('ASSIGNED', 'IN_PROGRESS',
                                          'PENDING_VENDOR', 'REOPENED')
                    GROUP BY assignee_id
                ) loads ON loads.assignee_id = u.user_id
                WHERE {where}
                ORDER BY active_load, u.last_assigned_at IS NOT NULL,
                         u.last_assigned_at, u.user_id
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        ).mappings().all()
        return rows, total
