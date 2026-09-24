import pytest
from pydantic import ValidationError

from app.domains.comments.schema import CommentCreateRequest


def test_comment_message_is_trimmed():
    request = CommentCreateRequest(message="  Update  ", visibility="USER_VISIBLE")
    assert request.message == "Update"


@pytest.mark.parametrize(
    "payload",
    [
        {"message": "   ", "visibility": "USER_VISIBLE"},
        {"message": "Update", "visibility": "VENDOR_SHARED"},
        {"message": "Update", "visibility": "USER_VISIBLE", "status": "CLOSED"},
    ],
)
def test_comment_request_rejects_invalid_payloads(payload):
    with pytest.raises(ValidationError):
        CommentCreateRequest(**payload)

