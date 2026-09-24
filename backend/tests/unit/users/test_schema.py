import pytest
from pydantic import ValidationError

from app.domains.users.schema import UpdateProfileRequest


def test_update_profile_requires_a_field():
    with pytest.raises(ValidationError):
        UpdateProfileRequest()


@pytest.mark.parametrize("payload", [{"display_name": None}, {"is_available": None}])
def test_update_profile_rejects_explicit_null(payload):
    with pytest.raises(ValidationError):
        UpdateProfileRequest.model_validate(payload)


def test_update_profile_rejects_unapproved_fields():
    with pytest.raises(ValidationError):
        UpdateProfileRequest.model_validate({"role": "SERVICE_DESK_MANAGER"})


def test_update_profile_rejects_blank_display_name():
    with pytest.raises(ValidationError):
        UpdateProfileRequest(display_name="   ")
