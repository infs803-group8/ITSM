"""Business rules for the three-step S3 attachment flow."""

from datetime import datetime, timedelta
from pathlib import PurePath
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.common.pagination import PaginationMeta
from app.common.request_context import RequestContext
from app.core.clock import as_mysql_utc, as_utc, utc_now
from app.core.config import get_settings
from app.core.enums import AttachmentUploadStatus, AttachmentVisibility
from app.core.errors import ApplicationError
from app.domains.attachments.access_policy import (
    AttachmentAccessPolicy,
    resource_not_found,
)
from app.domains.attachments.model import Attachment, AttachmentUpload
from app.domains.attachments.repository import AttachmentRepository
from app.domains.attachments.schema import (
    AttachmentData,
    AttachmentListResponse,
    AttachmentResponse,
    CompleteUploadRequest,
    DownloadData,
    DownloadResponse,
    PresignData,
    PresignRequest,
    PresignResponse,
)
from app.integrations.s3.object_verification import ObjectNotReadyError, ObjectStorageError
from app.integrations.s3.presigned_urls import ObjectStorage


def attachment_data(attachment: Attachment) -> AttachmentData:
    return AttachmentData(
        attachment_id=UUID(attachment.attachment_id),
        ticket_id=attachment.ticket_id,
        file_name=attachment.file_name,
        content_type=attachment.verified_content_type,
        size_bytes=attachment.verified_size,
        visibility=attachment.visibility,
        created_at=as_utc(attachment.created_at),
    )


class AttachmentService:
    def __init__(self, database: Session, storage: ObjectStorage | None) -> None:
        self.database = database
        self.repository = AttachmentRepository(database)
        self.storage = storage
        self.policy = AttachmentAccessPolicy()

    @staticmethod
    def _extension(file_name: str) -> str:
        cleaned = file_name.strip()
        if cleaned != file_name or not cleaned or "/" in cleaned or "\\" in cleaned:
            raise ApplicationError(
                "VALIDATION_ERROR",
                "file_name must be a base file name without a path.",
                422,
            )
        suffix = PurePath(cleaned).suffix.lower().removeprefix(".")
        if not suffix:
            raise ApplicationError(
                "UNSUPPORTED_ATTACHMENT_TYPE",
                "The attachment file extension is not supported.",
                422,
            )
        return suffix

    @staticmethod
    def _storage_unavailable() -> ApplicationError:
        return ApplicationError(
            "STORAGE_UNAVAILABLE",
            "Object storage is temporarily unavailable.",
            503,
        )

    def create_upload_session(
        self,
        ticket_id: int,
        actor: RequestContext,
        request: PresignRequest,
    ) -> PresignResponse:
        try:
            config = self.repository.get_config()
            ticket = self.repository.get_ticket_access(ticket_id, actor, for_update=True)
            vendor_request_id, vendor_org_id = self.policy.ensure_ticket_write(
                ticket, actor, request.visibility
            )
            if request.size_bytes > config.max_size_bytes:
                raise ApplicationError(
                    "ATTACHMENT_TOO_LARGE",
                    f"The attachment exceeds the {config.max_size_bytes} byte limit.",
                    413,
                )
            extension = self._extension(request.file_name)
            if not self.repository.is_type_allowed(extension, request.content_type.value):
                raise ApplicationError(
                    "UNSUPPORTED_ATTACHMENT_TYPE",
                    "The file extension and content type combination is not supported.",
                    422,
                )

            now = utc_now()
            upload_id = str(uuid4())
            settings = get_settings()
            prefix = settings.s3_key_prefix.strip("/") or settings.environment
            object_key = f"{prefix}/pending/{ticket_id}/{upload_id}"
            expires_at = now + timedelta(seconds=config.upload_ttl_seconds)
            upload = AttachmentUpload(
                upload_id=upload_id,
                ticket_id=ticket_id,
                creator_id=actor.user_id,
                object_key=object_key,
                file_name=request.file_name,
                expected_content_type=request.content_type.value,
                expected_size=request.size_bytes,
                visibility=request.visibility.value,
                vendor_request_id=vendor_request_id,
                vendor_org_id=vendor_org_id,
                status=AttachmentUploadStatus.PENDING.value,
                expires_at=as_mysql_utc(expires_at),
            )
            self.repository.add_upload(upload)
            try:
                assert self.storage is not None
                upload_url = self.storage.create_upload_url(
                    object_key=object_key,
                    content_type=request.content_type.value,
                    expires_in=config.upload_ttl_seconds,
                )
            except ObjectStorageError:
                self.database.rollback()
                raise self._storage_unavailable() from None
            self.database.commit()
            return PresignResponse(
                data=PresignData(
                    upload_id=UUID(upload_id),
                    upload_url=upload_url,
                    signed_headers={"Content-Type": request.content_type.value},
                    expires_at=expires_at,
                )
            )
        except Exception:
            if self.database.in_transaction():
                self.database.rollback()
            raise

    def _mark_and_raise(
        self,
        upload: AttachmentUpload,
        status: AttachmentUploadStatus,
        code: str,
        message: str,
        status_code: int,
        now: datetime,
    ) -> None:
        upload.status = status.value
        if status == AttachmentUploadStatus.EXPIRED:
            upload.expired_at = as_mysql_utc(now)
        else:
            upload.aborted_at = as_mysql_utc(now)
        self.database.commit()
        raise ApplicationError(code, message, status_code)

    def complete_upload(
        self,
        ticket_id: int,
        actor: RequestContext,
        request: CompleteUploadRequest,
    ) -> AttachmentResponse:
        upload_id = str(request.upload_id)
        upload = self.repository.get_upload(upload_id)
        if upload is None or upload.ticket_id != ticket_id or upload.creator_id != actor.user_id:
            self.database.rollback()
            raise resource_not_found()
        if upload.status == AttachmentUploadStatus.COMPLETED.value:
            attachment = self.repository.get_attachment_by_upload(upload_id)
            if attachment is None:
                self.database.rollback()
                raise ApplicationError(
                    "SERVICE_UNAVAILABLE",
                    "Completed attachment metadata is unavailable.",
                    503,
                )
            self.database.rollback()
            return AttachmentResponse(data=attachment_data(attachment))
        if upload.status == AttachmentUploadStatus.EXPIRED.value:
            self.database.rollback()
            raise ApplicationError(
                "UPLOAD_SESSION_EXPIRED",
                "The attachment upload session has expired.",
                409,
            )
        if upload.status == AttachmentUploadStatus.ABORTED.value:
            self.database.rollback()
            raise ApplicationError(
                "UPLOAD_INTEGRITY_MISMATCH",
                "The attachment upload session was aborted.",
                409,
            )

        now = utc_now()
        if as_utc(upload.expires_at) <= now:
            self._mark_and_raise(
                upload,
                AttachmentUploadStatus.EXPIRED,
                "UPLOAD_SESSION_EXPIRED",
                "The attachment upload session has expired.",
                409,
                now,
            )
        object_key = upload.object_key
        self.database.rollback()  # Never hold a database lock while calling S3.
        try:
            assert self.storage is not None
            object_info = self.storage.head_object(object_key=object_key)
        except ObjectNotReadyError:
            raise ApplicationError(
                "UPLOAD_NOT_READY",
                "The uploaded object is not available yet.",
                409,
            ) from None
        except ObjectStorageError:
            raise self._storage_unavailable() from None

        try:
            # Frozen lock order: Ticket first, then AttachmentUpload.
            ticket = self.repository.get_ticket_access(ticket_id, actor, for_update=True)
            upload = self.repository.get_upload(upload_id, for_update=True)
            if (
                upload is None
                or upload.ticket_id != ticket_id
                or upload.creator_id != actor.user_id
            ):
                raise resource_not_found()
            if upload.status == AttachmentUploadStatus.COMPLETED.value:
                attachment = self.repository.get_attachment_by_upload(upload_id)
                if attachment is None:
                    raise ApplicationError(
                        "SERVICE_UNAVAILABLE",
                        "Completed attachment metadata is unavailable.",
                        503,
                    )
                self.database.rollback()
                return AttachmentResponse(data=attachment_data(attachment))

            now = utc_now()
            if (
                upload.status == AttachmentUploadStatus.EXPIRED.value
                or as_utc(upload.expires_at) <= now
            ):
                self._mark_and_raise(
                    upload,
                    AttachmentUploadStatus.EXPIRED,
                    "UPLOAD_SESSION_EXPIRED",
                    "The attachment upload session has expired.",
                    409,
                    now,
                )
            if upload.status != AttachmentUploadStatus.PENDING.value:
                raise ApplicationError(
                    "UPLOAD_INTEGRITY_MISMATCH",
                    "The attachment upload session cannot be completed.",
                    409,
                )

            visibility = AttachmentVisibility(upload.visibility)
            try:
                self.policy.ensure_ticket_write(ticket, actor, visibility)
            except ApplicationError as exc:
                if exc.code in {"TICKET_CLOSED", "NO_ACTIVE_VENDOR_REQUEST"}:
                    self._mark_and_raise(
                        upload,
                        AttachmentUploadStatus.ABORTED,
                        exc.code,
                        exc.message,
                        exc.status_code,
                        now,
                    )
                raise
            if (
                visibility == AttachmentVisibility.VENDOR_SHARED
                and not self.repository.vendor_binding_is_active(upload)
            ):
                self._mark_and_raise(
                    upload,
                    AttachmentUploadStatus.ABORTED,
                    "NO_ACTIVE_VENDOR_REQUEST",
                    "The vendor request is no longer active.",
                    409,
                    now,
                )
            if (
                object_info.size_bytes != upload.expected_size
                or object_info.content_type != upload.expected_content_type
            ):
                self._mark_and_raise(
                    upload,
                    AttachmentUploadStatus.ABORTED,
                    "UPLOAD_INTEGRITY_MISMATCH",
                    "The uploaded object does not match the approved file attributes.",
                    409,
                    now,
                )

            attachment = Attachment(
                attachment_id=str(uuid4()),
                upload_id=upload.upload_id,
                ticket_id=upload.ticket_id,
                creator_id=upload.creator_id,
                object_key=upload.object_key,
                file_name=upload.file_name,
                verified_content_type=object_info.content_type,
                verified_size=object_info.size_bytes,
                visibility=upload.visibility,
                vendor_request_id=upload.vendor_request_id,
                vendor_org_id=upload.vendor_org_id,
                created_at=as_mysql_utc(now),
            )
            self.repository.add_attachment(attachment)
            upload.status = AttachmentUploadStatus.COMPLETED.value
            upload.completed_at = as_mysql_utc(now)
            upload.attachment_id = attachment.attachment_id
            self.repository.add_attachment_event(attachment, actor.user_id)
            self.database.commit()
            return AttachmentResponse(data=attachment_data(attachment))
        except Exception:
            if self.database.in_transaction():
                self.database.rollback()
            raise

    def list_attachments(
        self,
        ticket_id: int,
        actor: RequestContext,
        *,
        page: int,
        page_size: int,
        visibility: AttachmentVisibility | None,
    ) -> AttachmentListResponse:
        ticket = self.repository.get_ticket_access(ticket_id, actor)
        self.policy.ensure_ticket_read(ticket, actor)
        allowed = self.policy.resolve_visibility_filter(actor, visibility)
        items, total = self.repository.list_attachments(
            ticket_id, allowed, actor, page=page, page_size=page_size
        )
        return AttachmentListResponse(
            data=[attachment_data(item) for item in items],
            meta=PaginationMeta.from_total(page=page, page_size=page_size, total=total),
        )

    def create_download(
        self,
        ticket_id: int,
        attachment_id: UUID,
        actor: RequestContext,
    ) -> DownloadResponse:
        config = self.repository.get_config()
        ticket = self.repository.get_ticket_access(ticket_id, actor)
        self.policy.ensure_ticket_read(ticket, actor)
        attachment = self.repository.get_attachment(ticket_id, str(attachment_id))
        visibilities = self.policy.readable_visibilities(actor)
        if attachment is None or not self.repository.attachment_is_visible(
            attachment, visibilities, actor
        ):
            raise resource_not_found()
        try:
            assert self.storage is not None
            url = self.storage.create_download_url(
                object_key=attachment.object_key,
                file_name=attachment.file_name,
                content_type=attachment.verified_content_type,
                expires_in=config.download_ttl_seconds,
            )
        except ObjectStorageError:
            raise self._storage_unavailable() from None
        return DownloadResponse(
            data=DownloadData(
                attachment_id=UUID(attachment.attachment_id),
                file_name=attachment.file_name,
                content_type=attachment.verified_content_type,
                download_url=url,
                expires_at=utc_now() + timedelta(seconds=config.download_ttl_seconds),
            )
        )
