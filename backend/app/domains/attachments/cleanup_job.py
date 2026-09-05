"""Idempotent cleanup for expired or aborted attachment upload sessions."""

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.clock import as_mysql_utc, utc_now
from app.core.enums import AttachmentUploadStatus
from app.db.session import SessionLocal
from app.domains.attachments.repository import AttachmentRepository
from app.integrations.s3.object_verification import ObjectStorageError
from app.integrations.s3.presigned_urls import ObjectStorage, S3ObjectStorage

logger = logging.getLogger(__name__)


class AttachmentCleanupService:
    def __init__(self, database: Session, storage: ObjectStorage) -> None:
        self.database = database
        self.repository = AttachmentRepository(database)
        self.storage = storage

    def run_once(self, *, limit: int = 200) -> tuple[int, int]:
        """Visit every eligible session; ``limit`` is the database page size.

        Keep terminal sessions retryable: a PUT started before URL expiry may
        finish after an earlier DELETE. A stable keyset cursor lets later pages
        progress even when old objects are already absent or deletion fails.
        """
        if limit < 1:
            raise ValueError("Cleanup page size must be positive")
        now = as_mysql_utc(utc_now())
        expired = 0
        deleted = 0
        after_upload_id = ""
        while True:
            candidates = self.repository.get_cleanup_candidates(
                now, limit, after_upload_id=after_upload_id
            )
            upload_ids = [candidate.upload_id for candidate in candidates]
            self.database.rollback()
            if not upload_ids:
                break
            for upload_id in upload_ids:
                newly_expired, removed = self._clean_upload(upload_id, now)
                expired += newly_expired
                deleted += removed
            after_upload_id = upload_ids[-1]
        return expired, deleted

    def _clean_upload(self, upload_id: str, now: datetime) -> tuple[int, int]:
        expired = 0
        try:
            upload = self.repository.get_upload(upload_id, for_update=True)
            if upload is None:
                self.database.rollback()
                return 0, 0
            if upload.status == AttachmentUploadStatus.PENDING.value:
                if upload.expires_at > now:
                    self.database.rollback()
                    return 0, 0
                upload.status = AttachmentUploadStatus.EXPIRED.value
                upload.expired_at = now
                expired = 1
            if (
                upload.status
                not in {
                    AttachmentUploadStatus.EXPIRED.value,
                    AttachmentUploadStatus.ABORTED.value,
                }
                or upload.attachment_id is not None
            ):
                self.database.rollback()
                return 0, 0
            object_key = upload.object_key
            self.database.commit()

            # Delete after the status commit. S3 DELETE is idempotent, so a failed
            # invocation can safely retry the same row on the next scheduled run.
            try:
                self.storage.delete_object(object_key=object_key)
                return expired, 1
            except ObjectStorageError:
                logger.warning("Could not delete orphan S3 object for upload %s", upload_id)
                return expired, 0
        except Exception:
            self.database.rollback()
            raise


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as database:
        expired, deleted = AttachmentCleanupService(database, S3ObjectStorage()).run_once()
        logger.info("Attachment cleanup finished: expired=%d deleted=%d", expired, deleted)


if __name__ == "__main__":
    main()
