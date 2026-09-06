from datetime import datetime

import pytest

from app.core.errors import ApplicationError
from app.core.security import hash_password
from app.domains.auth.schema import LoginRequest, RegisterRequest
from app.domains.auth.service import AuthService
from app.domains.users.model import User


class FakeDatabase:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class FakeAuthRepository:
    def __init__(self, existing: User | None = None):
        self.existing = existing
        self.added: User | None = None

    def get_by_email(self, _email: str):
        return self.existing

    def add(self, user: User):
        user.user_id = 101
        user.created_at = datetime(2026, 9, 7, 1, 0, 0)
        self.added = user
        return user


def test_register_forces_user_role_and_hashes_password():
    database = FakeDatabase()
    service = AuthService(database)  # type: ignore[arg-type]
    repository = FakeAuthRepository()
    service.repository = repository  # type: ignore[assignment]

    response = service.register(
        RegisterRequest(
            email="NEW.User@Example.com",
            password="ExamplePass123!",
            display_name=" New User ",
        )
    )

    assert response.data.role == "USER"
    assert repository.added is not None
    assert repository.added.email == "new.user@example.com"
    assert repository.added.display_name == "New User"
    assert repository.added.password_hash != "ExamplePass123!"
    assert database.commits == 1


def test_register_rejects_duplicate_email():
    database = FakeDatabase()
    service = AuthService(database)  # type: ignore[arg-type]
    service.repository = FakeAuthRepository(User())  # type: ignore[assignment]

    with pytest.raises(ApplicationError) as error:
        service.register(
            RegisterRequest(
                email="user@example.com",
                password="ExamplePass123!",
                display_name="User",
            )
        )

    assert error.value.code == "EMAIL_ALREADY_REGISTERED"
    assert error.value.status_code == 409


def test_login_returns_token_and_never_exposes_password_hash():
    database = FakeDatabase()
    user = User(
        user_id=101,
        email="user@example.com",
        password_hash=hash_password("ExamplePass123!"),
        display_name="User",
        role_code="USER",
        is_available=None,
        vendor_org_id=None,
        is_active=True,
        created_at=datetime(2026, 9, 7, 1, 0, 0),
    )
    service = AuthService(database)  # type: ignore[arg-type]
    service.repository = FakeAuthRepository(user)  # type: ignore[assignment]

    response = service.login(
        LoginRequest(email="USER@example.com", password="ExamplePass123!")
    )
    payload = response.model_dump()

    assert response.data.token_type == "bearer"
    assert response.data.expires_in > 0
    assert response.data.user.user_id == 101
    assert "password" not in str(payload).lower()


def test_login_uses_same_error_for_unknown_user_and_wrong_password():
    database = FakeDatabase()
    for existing in (None, User(is_active=True, password_hash=hash_password("correct-pass"))):
        service = AuthService(database)  # type: ignore[arg-type]
        service.repository = FakeAuthRepository(existing)  # type: ignore[assignment]
        with pytest.raises(ApplicationError) as error:
            service.login(LoginRequest(email="user@example.com", password="wrong-pass"))
        assert error.value.code == "INVALID_CREDENTIALS"
        assert error.value.status_code == 401
