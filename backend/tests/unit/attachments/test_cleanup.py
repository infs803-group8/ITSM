from datetime import UTC, datetime

from app.core.clock import as_mysql_utc
from app.core.enums import AttachmentUploadStatus
from app.domains.attachments.cleanup_job import AttachmentCleanupService
from tests.unit.attachments.test_service import FakeSession, FakeStorage, make_upload


class CleanupRepository:
    def __init__(self, uploads):
        self.uploads = {item.upload_id: item for item in uploads}

    def get_cleanup_candidates(self, _now, _limit):
        return list(self.uploads.values())

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
