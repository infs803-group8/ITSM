import pytest
from pydantic import ValidationError

from app.domains.auth.schema import LoginRequest, RegisterRequest


def test_register_request_rejects_extra_role_field():
    with pytest.raises(ValidationError):
        RegisterRequest.model_validate(
            {
                "email": "user@example.com",
                "password": "ExamplePass123!",
                "display_name": "Example User",
                "role": "SERVICE_DESK_MANAGER",
            }
        )


def test_register_request_enforces_password_length():
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="user@example.com", password="short", display_name="Example User"
        )


def test_register_request_rejects_blank_display_name():
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="user@example.com",
            password="ExamplePass123!",
            display_name="   ",
        )


def test_login_request_normal_shape():
    request = LoginRequest(email="USER@example.com", password="ExamplePass123!")
    assert str(request.email) == "USER@example.com"
