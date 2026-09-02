from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.common.request_context import RequestContext
from app.core.clock import as_mysql_utc
from app.core.enums import AttachmentUploadStatus, AttachmentVisibility, UserRole
from app.core.errors import ApplicationError
from app.domains.attachments.access_policy import TicketAccessRecord
from app.domains.attachments.model import AttachmentUpload
from app.domains.attachments.repository import AttachmentConfigRecord
from app.domains.attachments.schema import CompleteUploadRequest, PresignRequest
from app.domains.attachments.service import AttachmentService
from app.integrations.s3.object_verification import ObjectInfo, ObjectNotReadyError


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def in_transaction(self) -> bool:
        return False


class FakeStorage:
    def __init__(self, info: ObjectInfo | None = None) -> None:
        self.info = info or ObjectInfo(size_bytes=100, content_type="text/plain")
        self.head_calls = 0
        self.deleted: list[str] = []

    def create_upload_url(self, **_kwargs) -> str:
        return "https://example.test/upload"

    def head_object(self, **_kwargs) -> ObjectInfo:
        self.head_calls += 1
        return self.info

    def create_download_url(self, **_kwargs) -> str:
        return "https://example.test/download"

    def delete_object(self, *, object_key: str) -> None:
        self.deleted.append(object_key)


class FakeRepository:
    def __init__(self, upload: AttachmentUpload | None = None) -> None:
        self.upload = upload
        self.attachment = None
        self.events = 0
        self.vendor_active = True
        self.ticket = TicketAccessRecord(
            ticket_id=10,
            requester_id=1,
            assignee_id=2,
            status_code="IN_PROGRESS",
            active_vendor_request_id=90,
            active_vendor_org_id=8,
        )

    def get_config(self) -> AttachmentConfigRecord:
        return AttachmentConfigRecord(10_485_760, 900, 300)

    def get_ticket_access(self, *_args, **_kwargs):
        return self.ticket

    def is_type_allowed(self, extension: str, content_type: str) -> bool:
        return (extension, content_type) == ("log", "text/plain")

    def add_upload(self, upload: AttachmentUpload) -> None:
        self.upload = upload

    def get_upload(self, upload_id: str, **_kwargs):
        if self.upload is not None and self.upload.upload_id == upload_id:
            return self.upload
        return None

    def get_attachment_by_upload(self, _upload_id: str):
        return self.attachment

    def add_attachment(self, attachment) -> None:
        self.attachment = attachment

    def add_attachment_event(self, _attachment, _actor_id: int) -> None:
        self.events += 1

    def vendor_binding_is_active(self, _upload) -> bool:
        return self.vendor_active


def make_upload(*, creator_id: int = 1, expires_delta: int = 600) -> AttachmentUpload:
    now = datetime.now(UTC)
    return AttachmentUpload(
        upload_id=str(uuid4()),
        ticket_id=10,
        creator_id=creator_id,
        object_key=f"development/pending/10/{uuid4()}",
        file_name="router.log",
        expected_content_type="text/plain",
        expected_size=100,
        visibility=AttachmentVisibility.USER_VISIBLE.value,
        status=AttachmentUploadStatus.PENDING.value,
        expires_at=as_mysql_utc(now + timedelta(seconds=expires_delta)),
        created_at=as_mysql_utc(now),
        updated_at=as_mysql_utc(now),
    )


def service_with(upload=None, storage=None):
    session = FakeSession()
    service = AttachmentService(session, storage or FakeStorage())
    repository = FakeRepository(upload)
    service.repository = repository
    return service, repository, session


def test_presign_creates_persistent_pending_session():
    service, repository, session = service_with()
    response = service.create_upload_session(
        10,
        RequestContext(user_id=1, role=UserRole.USER),
        PresignRequest(
            file_name="router.log",
            content_type="text/plain",
            size_bytes=100,
            visibility="USER_VISIBLE",
        ),
    )
    assert repository.upload.status == "PENDING"
    assert repository.upload.creator_id == 1
    assert repository.upload.object_key.startswith("development/pending/10/")
    assert "router.log" not in repository.upload.object_key
    assert response.data.signed_headers == {"Content-Type": "text/plain"}
    assert session.commits == 1


def test_complete_is_atomic_and_idempotent():
    upload = make_upload()
    storage = FakeStorage()
    service, repository, session = service_with(upload, storage)
    actor = RequestContext(user_id=1, role=UserRole.USER)
    request = CompleteUploadRequest(upload_id=upload.upload_id)

    first = service.complete_upload(10, actor, request)
    second = service.complete_upload(10, actor, request)

    assert first == second
    assert upload.status == "COMPLETED"
    assert upload.attachment_id == str(first.data.attachment_id)
    assert repository.events == 1
    assert storage.head_calls == 1
    assert session.commits == 1


def test_complete_rejects_another_users_session_as_not_found():
    upload = make_upload(creator_id=2)
    service, _repository, _session = service_with(upload)
    with pytest.raises(ApplicationError) as error:
        service.complete_upload(
            10,
            RequestContext(user_id=1, role=UserRole.USER),
            CompleteUploadRequest(upload_id=upload.upload_id),
        )
    assert error.value.code == "RESOURCE_NOT_FOUND"


def test_complete_marks_mismatched_object_aborted():
    upload = make_upload()
    storage = FakeStorage(ObjectInfo(size_bytes=101, content_type="text/plain"))
    service, repository, session = service_with(upload, storage)
    with pytest.raises(ApplicationError) as error:
        service.complete_upload(
            10,
            RequestContext(user_id=1, role=UserRole.USER),
            CompleteUploadRequest(upload_id=upload.upload_id),
        )
    assert error.value.code == "UPLOAD_INTEGRITY_MISMATCH"
    assert upload.status == "ABORTED"
    assert repository.attachment is None
    assert repository.events == 0
    assert session.commits == 1


def test_complete_marks_session_aborted_if_ticket_closed_after_presign():
    upload = make_upload()
    service, repository, _session = service_with(upload)
    repository.ticket = TicketAccessRecord(
        ticket_id=10,
        requester_id=1,
        assignee_id=None,
        status_code="CLOSED",
        active_vendor_request_id=None,
        active_vendor_org_id=None,
    )
    with pytest.raises(ApplicationError) as error:
        service.complete_upload(
            10,
            RequestContext(user_id=1, role=UserRole.USER),
            CompleteUploadRequest(upload_id=upload.upload_id),
        )
    assert error.value.code == "TICKET_CLOSED"
    assert upload.status == "ABORTED"


def test_complete_marks_vendor_upload_aborted_if_active_request_ended():
    upload = make_upload(creator_id=2)
    upload.visibility = AttachmentVisibility.VENDOR_SHARED.value
    upload.vendor_request_id = 90
    upload.vendor_org_id = 8
    service, repository, _session = service_with(upload)
    repository.ticket = TicketAccessRecord(
        ticket_id=10,
        requester_id=1,
        assignee_id=2,
        status_code="PENDING_VENDOR",
        active_vendor_request_id=None,
        active_vendor_org_id=None,
    )
    with pytest.raises(ApplicationError) as error:
        service.complete_upload(
            10,
            RequestContext(user_id=2, role=UserRole.ENGINEER_TIER2),
            CompleteUploadRequest(upload_id=upload.upload_id),
        )
    assert error.value.code == "NO_ACTIVE_VENDOR_REQUEST"
    assert upload.status == "ABORTED"


def test_complete_expired_session_never_calls_s3():
    upload = make_upload(expires_delta=-1)
    storage = FakeStorage()
    service, _repository, _session = service_with(upload, storage)
    with pytest.raises(ApplicationError) as error:
        service.complete_upload(
            10,
            RequestContext(user_id=1, role=UserRole.USER),
            CompleteUploadRequest(upload_id=upload.upload_id),
        )
    assert error.value.code == "UPLOAD_SESSION_EXPIRED"
    assert upload.status == "EXPIRED"
    assert storage.head_calls == 0


def test_complete_reports_object_not_ready_without_aborting_session():
    class NotReadyStorage(FakeStorage):
        def head_object(self, **_kwargs):
            raise ObjectNotReadyError

    upload = make_upload()
    service, _repository, _session = service_with(upload, NotReadyStorage())
    with pytest.raises(ApplicationError) as error:
        service.complete_upload(
            10,
            RequestContext(user_id=1, role=UserRole.USER),
            CompleteUploadRequest(upload_id=upload.upload_id),
        )
    assert error.value.code == "UPLOAD_NOT_READY"
    assert upload.status == "PENDING"
