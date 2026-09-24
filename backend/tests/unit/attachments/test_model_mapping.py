from app.domains.attachments.model import Attachment, AttachmentUpload


def test_member_a_mappers_resolve_without_other_domain_models():
    """Regression: ORM flush must not require unfinished Member B/C models."""
    assert list(AttachmentUpload.__mapper__._sorted_tables) == [AttachmentUpload.__table__]
    assert list(Attachment.__mapper__._sorted_tables) == [Attachment.__table__]


def test_intra_domain_foreign_keys_remain_mapped():
    upload_targets = {
        foreign_key.target_fullname for foreign_key in AttachmentUpload.__table__.foreign_keys
    }
    attachment_targets = {
        foreign_key.target_fullname for foreign_key in Attachment.__table__.foreign_keys
    }
    assert upload_targets == {"attachments.attachment_id"}
    assert attachment_targets == {"attachment_uploads.upload_id"}
