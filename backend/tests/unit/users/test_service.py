from datetime import datetime

import pytest

from app.common.request_context import RequestContext
from app.core.errors import ApplicationError
from app.domains.users.model import User
from app.domains.users.schema import UpdateProfileRequest
from app.domains.users.service import UserService


class FakeDatabase:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def in_transaction(self):
        return False


class FakeUserRepository:
    def __init__(self, user: User):
        self.user = user
        self.flushed = False

    def get_active(self, _user_id: int, *, for_update: bool = False):
        return self.user

    def get_vendor_organisation(self, _vendor_org_id):
        return None

    def flush(self):
        self.flushed = True


def make_user(role: str, is_available: bool | None) -> User:
    return User(
        user_id=101,
        email="user@example.com",
        password_hash="not-serialized",
        display_name="Original Name",
        role_code=role,
        is_available=is_available,
        vendor_org_id=None,
        is_active=True,
        created_at=datetime(2026, 9, 7, 1, 0, 0),
    )


def test_engineer_can_update_name_and_availability():
    database = FakeDatabase()
    user = make_user("ENGINEER_TIER1", True)
    service = UserService(database)  # type: ignore[arg-type]
    repository = FakeUserRepository(user)
    service.repository = repository  # type: ignore[assignment]

    response = service.update_profile(
        RequestContext(user_id=101, role="ENGINEER_TIER1"),
        UpdateProfileRequest(display_name="Updated Name", is_available=False),
    )

    assert response.data.display_name == "Updated Name"
    assert response.data.is_available is False
    assert repository.flushed
    assert database.commits == 1


def test_non_engineer_cannot_update_availability():
    service = UserService(FakeDatabase())  # type: ignore[arg-type]
    service.repository = FakeUserRepository(make_user("USER", None))  # type: ignore[assignment]

    with pytest.raises(ApplicationError) as error:
        service.update_profile(
            RequestContext(user_id=101, role="USER"),
            UpdateProfileRequest(is_available=False),
        )

    assert error.value.code == "DATA_SCOPE_DENIED"
    assert error.value.status_code == 403
