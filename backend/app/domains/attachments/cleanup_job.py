"""Idempotent cleanup for expired or aborted attachment upload sessions."""

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.clock import as_mysql_utc
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
        now = datetime.now(UTC)
        candidates = self.repository.get_cleanup_candidates(as_mysql_utc(now), limit)
        upload_ids = [candidate.upload_id for candidate in candidates]
        self.database.rollback()
        expired = 0
        deleted = 0

        for upload_id in upload_ids:
            upload = self.repository.get_upload(upload_id, for_update=True)
            if upload is None:
                self.database.rollback()
                continue
            if upload.status == AttachmentUploadStatus.PENDING.value:
                if upload.expires_at > as_mysql_utc(now):
                    self.database.rollback()
                    continue
                upload.status = AttachmentUploadStatus.EXPIRED.value
                upload.expired_at = as_mysql_utc(now)
                expired += 1
            if upload.status not in {
                AttachmentUploadStatus.EXPIRED.value,
                AttachmentUploadStatus.ABORTED.value,
            } or upload.attachment_id is not None:
                self.database.rollback()
                continue
            object_key = upload.object_key
            self.database.commit()

            # Delete after the status commit. S3 DELETE is idempotent, so a failed
            # invocation can safely retry the same row on the next scheduled run.
            try:
                self.storage.delete_object(object_key=object_key)
                deleted += 1
            except ObjectStorageError:
                logger.warning("Could not delete orphan S3 object for upload %s", upload_id)

        return expired, deleted


def main() -> None:
    with SessionLocal() as database:
        expired, deleted = AttachmentCleanupService(database, S3ObjectStorage()).run_once()
        logger.info("Attachment cleanup finished: expired=%d deleted=%d", expired, deleted)


if __name__ == "__main__":
    main()
