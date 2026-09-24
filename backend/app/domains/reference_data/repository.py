"""Read-only reference-data and vendor directory queries."""

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


class ReferenceDataRepository:
    def __init__(self, database: Session) -> None:
        self.database = database

    def reference_data(self) -> tuple[Mapping[str, Any], Sequence[Mapping[str, Any]]]:
        config = self.database.execute(
            text("SELECT * FROM service_config WHERE config_id = 1")
        ).mappings().one()
        allowed_types = self.database.execute(
            text(
                "SELECT extension, content_type FROM allowed_attachment_types "
                "WHERE is_active = 1 ORDER BY extension"
            )
        ).mappings().all()
        return config, allowed_types

    def list_vendors(
        self, *, page: int, page_size: int, search: str | None, is_active: bool | None
    ) -> tuple[Sequence[Mapping[str, Any]], int]:
        filters = []
        params: dict[str, Any] = {"limit": page_size, "offset": (page - 1) * page_size}
        if search is not None:
            filters.append("name LIKE :search")
            params["search"] = f"%{search}%"
        if is_active is not None:
            filters.append("is_active = :is_active")
            params["is_active"] = is_active
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        total = int(
            self.database.execute(
                text(f"SELECT COUNT(*) FROM vendor_organisations {where}"), params
            ).scalar_one()
        )
        rows = self.database.execute(
            text(
                "SELECT vendor_org_id, name, is_active FROM vendor_organisations "
                f"{where} ORDER BY name, vendor_org_id LIMIT :limit OFFSET :offset"
            ),
            params,
        ).mappings().all()
        return rows, total
