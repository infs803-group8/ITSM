"""Persistence operations for Member A's attachment domain."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, func, select, text
from sqlalchemy.orm import Session

from app.common.request_context import RequestContext
from app.core.enums import AttachmentUploadStatus, AttachmentVisibility, UserRole
from app.domains.attachments.access_policy import TicketAccessRecord
from app.domains.attachments.model import Attachment, AttachmentUpload


@dataclass(frozen=True)
class AttachmentConfigRecord:
    max_size_bytes: int
    upload_ttl_seconds: int
    download_ttl_seconds: int


class AttachmentRepository:
    def __init__(self, database: Session) -> None:
        self.database = database

    def get_ticket_access(
        self,
        ticket_id: int,
        actor: RequestContext,
        *,
        for_update: bool = False,
    ) -> TicketAccessRecord | None:
        lock = " FOR UPDATE" if for_update else ""
        row = self.database.execute(
            text(
                """
                SELECT t.ticket_id, t.requester_id, t.assignee_id, t.status_code,
                       active_vr.vendor_request_id AS active_vendor_request_id,
                       active_vr.vendor_org_id AS active_vendor_org_id,
                       EXISTS(
                           SELECT 1 FROM vendor_requests history_vr
                           WHERE history_vr.ticket_id = t.ticket_id
                             AND history_vr.vendor_org_id = :actor_vendor_org_id
                       ) AS actor_has_vendor_history
                FROM tickets t
                LEFT JOIN vendor_requests active_vr
                  ON active_vr.ticket_id = t.ticket_id AND active_vr.status = 'ACTIVE'
                WHERE t.ticket_id = :ticket_id
                """
                + lock
            ),
            {"ticket_id": ticket_id, "actor_vendor_org_id": actor.vendor_org_id or 0},
        ).mappings().one_or_none()
        if row is None:
            return None
        return TicketAccessRecord(
            ticket_id=int(row["ticket_id"]),
            requester_id=int(row["requester_id"]),
            assignee_id=int(row["assignee_id"]) if row["assignee_id"] is not None else None,
            status_code=str(row["status_code"]),
            active_vendor_request_id=(
                int(row["active_vendor_request_id"])
                if row["active_vendor_request_id"] is not None
                else None
            ),
            active_vendor_org_id=(
                int(row["active_vendor_org_id"])
                if row["active_vendor_org_id"] is not None
                else None
            ),
            actor_has_vendor_history=bool(row["actor_has_vendor_history"]),
        )

    def get_config(self) -> AttachmentConfigRecord:
        row = self.database.execute(
            text(
                """
                SELECT attachment_max_size_bytes, upload_url_ttl_seconds,
                       download_url_ttl_seconds
                FROM service_config WHERE config_id = 1
                """
            )
        ).mappings().one()
        return AttachmentConfigRecord(
            max_size_bytes=int(row["attachment_max_size_bytes"]),
            upload_ttl_seconds=int(row["upload_url_ttl_seconds"]),
            download_ttl_seconds=int(row["download_url_ttl_seconds"]),
        )

    def is_type_allowed(self, extension: str, content_type: str) -> bool:
        return self.database.execute(
            text(
                """
                SELECT 1 FROM allowed_attachment_types
                WHERE extension = :extension AND content_type = :content_type AND is_active = 1
                """
            ),
            {"extension": extension, "content_type": content_type},
        ).scalar_one_or_none() is not None

    def add_upload(self, upload: AttachmentUpload) -> None:
        self.database.add(upload)
        self.database.flush()

    def get_upload(self, upload_id: str, *, for_update: bool = False) -> AttachmentUpload | None:
        statement: Select[tuple[AttachmentUpload]] = select(AttachmentUpload).where(
            AttachmentUpload.upload_id == upload_id
        )
        if for_update:
            statement = statement.with_for_update()
        return self.database.execute(statement).scalar_one_or_none()

    def get_attachment_by_upload(self, upload_id: str) -> Attachment | None:
        return self.database.execute(
            select(Attachment).where(Attachment.upload_id == upload_id)
        ).scalar_one_or_none()

    def get_attachment(self, ticket_id: int, attachment_id: str) -> Attachment | None:
        return self.database.execute(
            select(Attachment).where(
                Attachment.ticket_id == ticket_id,
                Attachment.attachment_id == attachment_id,
            )
        ).scalar_one_or_none()

    @staticmethod
    def _visible_statement(
        ticket_id: int,
        visibilities: set[AttachmentVisibility],
        actor: RequestContext,
    ) -> Select[tuple[Attachment]]:
        statement = select(Attachment).where(
            Attachment.ticket_id == ticket_id,
            Attachment.visibility.in_([item.value for item in visibilities]),
        )
        if actor.role == UserRole.EXTERNAL_VENDOR:
            statement = statement.where(Attachment.vendor_org_id == actor.vendor_org_id)
        return statement

    def list_attachments(
        self,
        ticket_id: int,
        visibilities: set[AttachmentVisibility],
        actor: RequestContext,
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[Attachment], int]:
        base = self._visible_statement(ticket_id, visibilities, actor)
        total = int(
            self.database.execute(
                select(func.count()).select_from(base.order_by(None).subquery())
            ).scalar_one()
        )
        items = list(
            self.database.execute(
                base.order_by(Attachment.created_at.desc(), Attachment.attachment_id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).scalars()
        )
        return items, total

    @staticmethod
    def attachment_is_visible(
        attachment: Attachment,
        visibilities: set[AttachmentVisibility],
        actor: RequestContext,
    ) -> bool:
        if AttachmentVisibility(attachment.visibility) not in visibilities:
            return False
        return not (
            actor.role == UserRole.EXTERNAL_VENDOR
            and attachment.vendor_org_id != actor.vendor_org_id
        )

    def add_attachment(self, attachment: Attachment) -> None:
        self.database.add(attachment)
        self.database.flush()

    def add_attachment_event(self, attachment: Attachment, actor_id: int) -> None:
        scope = {
            AttachmentVisibility.USER_VISIBLE.value: "USER_VISIBLE",
            AttachmentVisibility.INTERNAL_ONLY.value: "INTERNAL_ONLY",
            AttachmentVisibility.VENDOR_SHARED.value: "VENDOR_SCOPE",
        }[attachment.visibility]
        self.database.execute(
            text(
                """
                INSERT INTO ticket_events
                    (ticket_id, event_type, scope, actor_id, vendor_org_id,
                     attachment_id, vendor_request_id, metadata)
                VALUES
                    (:ticket_id, 'ATTACHMENT_ADDED', :scope, :actor_id, :vendor_org_id,
                     :attachment_id, :vendor_request_id,
                     JSON_OBJECT('file_name', :file_name, 'content_type', :content_type,
                                 'size_bytes', :size_bytes, 'visibility', :visibility))
                """
            ),
            {
                "ticket_id": attachment.ticket_id,
                "scope": scope,
                "actor_id": actor_id,
                "vendor_org_id": attachment.vendor_org_id,
                "attachment_id": attachment.attachment_id,
                "vendor_request_id": attachment.vendor_request_id,
                "file_name": attachment.file_name,
                "content_type": attachment.verified_content_type,
                "size_bytes": attachment.verified_size,
                "visibility": attachment.visibility,
            },
        )

    def vendor_binding_is_active(self, upload: AttachmentUpload) -> bool:
        if upload.vendor_request_id is None or upload.vendor_org_id is None:
            return False
        return self.database.execute(
            text(
                """
                SELECT 1 FROM vendor_requests
                WHERE vendor_request_id = :vendor_request_id AND ticket_id = :ticket_id
                  AND vendor_org_id = :vendor_org_id AND status = 'ACTIVE'
                """
            ),
            {
                "vendor_request_id": upload.vendor_request_id,
                "ticket_id": upload.ticket_id,
                "vendor_org_id": upload.vendor_org_id,
            },
        ).scalar_one_or_none() is not None

    def get_cleanup_candidates(
        self, now: datetime, limit: int, *, after_upload_id: str = ""
    ) -> list[AttachmentUpload]:
        return list(
            self.database.execute(
                select(AttachmentUpload)
                .where(
                    AttachmentUpload.upload_id > after_upload_id,
                    AttachmentUpload.created_at <= now,
                    (
                        (AttachmentUpload.status == AttachmentUploadStatus.PENDING.value)
                        & (AttachmentUpload.expires_at <= now)
                    )
                    | AttachmentUpload.status.in_(
                        [
                            AttachmentUploadStatus.EXPIRED.value,
                            AttachmentUploadStatus.ABORTED.value,
                        ]
                    )
                )
                .order_by(AttachmentUpload.upload_id)
                .limit(limit)
            ).scalars()
        )
