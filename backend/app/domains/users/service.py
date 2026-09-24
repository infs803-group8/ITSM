"""Current-user profile business rules."""

from sqlalchemy.orm import Session

from app.common.pagination import PaginationMeta
from app.common.request_context import RequestContext
from app.core.clock import as_utc
from app.core.enums import Category, UserRole
from app.core.errors import ApplicationError
from app.domains.users.model import User
from app.domains.users.repository import UserRepository
from app.domains.users.schema import (
    AssigneeListResponse,
    AssigneeSummary,
    UpdateProfileRequest,
    UserProfile,
    UserResponse,
    VendorOrganisationView,
)


def profile_for(user: User, database: Session | None = None) -> UserProfile:
    vendor_view = None
    if database is not None and user.vendor_org_id is not None:
        vendor = UserRepository(database).get_vendor_organisation(user.vendor_org_id)
        if vendor is not None:
            vendor_view = VendorOrganisationView(
                vendor_org_id=vendor.vendor_org_id,
                name=vendor.name,
                is_active=vendor.is_active,
            )
    return UserProfile(
        user_id=user.user_id,
        email=user.email,
        display_name=user.display_name,
        role=UserRole(user.role_code),
        is_available=user.is_available,
        vendor_org=vendor_view,
        created_at=as_utc(user.created_at),
    )


class UserService:
    def __init__(self, database: Session) -> None:
        self.database = database
        self.repository = UserRepository(database)

    def _current_user(self, actor: RequestContext, *, for_update: bool = False) -> User:
        user = self.repository.get_active(actor.user_id, for_update=for_update)
        if user is None:
            raise ApplicationError(
                "INVALID_ACCESS_TOKEN", "The access token is invalid or expired.", 401
            )
        return user

    def get_profile(self, actor: RequestContext) -> UserResponse:
        return UserResponse(data=profile_for(self._current_user(actor), self.database))

    def update_profile(
        self, actor: RequestContext, request: UpdateProfileRequest
    ) -> UserResponse:
        try:
            user = self._current_user(actor, for_update=True)
            if "is_available" in request.model_fields_set and user.role_code not in {
                UserRole.ENGINEER_TIER1.value,
                UserRole.ENGINEER_TIER2.value,
            }:
                raise ApplicationError(
                    "DATA_SCOPE_DENIED",
                    "Only engineers may update availability.",
                    403,
                )
            if "display_name" in request.model_fields_set:
                assert request.display_name is not None
                user.display_name = request.display_name.strip()
            if "is_available" in request.model_fields_set:
                assert request.is_available is not None
                user.is_available = request.is_available
            self.repository.flush()
            self.database.commit()
            return UserResponse(data=profile_for(user, self.database))
        except Exception:
            if self.database.in_transaction():
                self.database.rollback()
            raise

    def list_assignees(
        self,
        actor: RequestContext,
        *,
        page: int,
        page_size: int,
        tier: str | None,
        category: Category | None,
        is_available: bool | None,
    ) -> AssigneeListResponse:
        if actor.role not in {
            UserRole.ENGINEER_TIER1,
            UserRole.ENGINEER_TIER2,
            UserRole.SERVICE_DESK_MANAGER,
        }:
            raise ApplicationError(
                "DATA_SCOPE_DENIED", "Assignee directory access is not permitted.", 403
            )
        rows, total = self.repository.list_assignees(
            page=page,
            page_size=page_size,
            tier=tier,
            category=category.value if category else None,
            is_available=is_available,
        )
        return AssigneeListResponse(
            data=[
                AssigneeSummary(
                    user_id=int(row["user_id"]),
                    display_name=str(row["display_name"]),
                    tier="TIER1"
                    if row["role_code"] == UserRole.ENGINEER_TIER1
                    else "TIER2",
                    skills=[
                        Category(item)
                        for item in str(row["skill_codes"]).split(",")
                        if item
                    ],
                    is_available=bool(row["is_available"]),
                    active_load=int(row["active_load"]),
                )
                for row in rows
            ],
            meta=PaginationMeta.from_total(page=page, page_size=page_size, total=total),
        )
