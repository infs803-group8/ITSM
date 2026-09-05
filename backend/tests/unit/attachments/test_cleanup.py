from datetime import UTC, datetime

from app.core.clock import as_mysql_utc
from app.core.enums import AttachmentUploadStatus
from app.domains.attachments.cleanup_job import AttachmentCleanupService
from tests.unit.attachments.test_service import FakeSession, FakeStorage, make_upload


class CleanupRepository:
    def __init__(self, uploads):
        self.uploads = {item.upload_id: item for item in uploads}

    def get_cleanup_candidates(self, _now, limit, *, after_upload_id=""):
        return [self.uploads[key] for key in sorted(self.uploads) if key > after_upload_id][:limit]

    def get_upload(self, upload_id, **_kwargs):
        return self.uploads.get(upload_id)


def test_cleanup_deletes_orphans_but_never_completed_objects():
    expired = make_upload(expires_delta=-1)
    completed = make_upload(expires_delta=-1)
    completed.status = AttachmentUploadStatus.COMPLETED.value
    completed.attachment_id = "dc208b68-90e9-405e-b3ac-a064f0ff2e11"
    storage = FakeStorage()
    service = AttachmentCleanupService(FakeSession(), storage)
    service.repository = CleanupRepository([expired, completed])

    expired_count, deleted_count = service.run_once()

    assert expired_count == 1
    assert deleted_count == 1
    assert expired.status == AttachmentUploadStatus.EXPIRED.value
    assert expired.expired_at <= as_mysql_utc(datetime.now(UTC))
    assert storage.deleted == [expired.object_key]


def test_cleanup_visits_later_pages_and_retries_on_next_run():
    uploads = [make_upload(expires_delta=-1) for _ in range(201)]
    for upload in uploads:
        upload.status = AttachmentUploadStatus.EXPIRED.value
    storage = FakeStorage()
    service = AttachmentCleanupService(FakeSession(), storage)
    service.repository = CleanupRepository(uploads)

    assert service.run_once() == (0, 201)
    assert set(storage.deleted) == {upload.object_key for upload in uploads}
    # Repeated deletion remains safe and catches late PUTs after earlier cleanup.
    assert service.run_once() == (0, 201)


def test_cleanup_failure_does_not_block_later_pages():
    from app.integrations.s3.object_verification import ObjectStorageError

    uploads = sorted(
        [make_upload(expires_delta=-1) for _ in range(3)], key=lambda item: item.upload_id
    )

    class FailingStorage(FakeStorage):
        def delete_object(self, *, object_key):
            if object_key == uploads[0].object_key:
                raise ObjectStorageError
            super().delete_object(object_key=object_key)

    storage = FailingStorage()
    service = AttachmentCleanupService(FakeSession(), storage)
    service.repository = CleanupRepository(uploads)
    assert service.run_once(limit=1) == (3, 2)
    assert storage.deleted == [item.object_key for item in uploads[1:]]


def test_cleanup_rechecks_completed_state_after_candidate_query():
    upload = make_upload(expires_delta=-1)

    class CompletedConcurrently(CleanupRepository):
        def get_upload(self, upload_id, **kwargs):
            row = super().get_upload(upload_id, **kwargs)
            row.status = AttachmentUploadStatus.COMPLETED.value
            row.attachment_id = "dc208b68-90e9-405e-b3ac-a064f0ff2e11"
            return row

    storage = FakeStorage()
    service = AttachmentCleanupService(FakeSession(), storage)
    service.repository = CompletedConcurrently([upload])
    assert service.run_once() == (0, 0)
    assert storage.deleted == []
