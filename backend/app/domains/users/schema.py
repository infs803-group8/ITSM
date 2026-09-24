"""API-10 and API-11 request/response schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.common.pagination import PaginationMeta
from app.core.enums import Category, UserRole


class VendorOrganisationView(BaseModel):
    vendor_org_id: int
    name: str
    is_active: bool


class UserProfile(BaseModel):
    user_id: int
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=100)
    role: UserRole
    is_available: bool | None
    vendor_org: VendorOrganisationView | None
    created_at: datetime


class UserResponse(BaseModel):
    data: UserProfile


class UpdateProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    is_available: bool | None = None

    @field_validator("display_name")
    @classmethod
    def display_name_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("display_name must not be blank")
        return value

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "UpdateProfileRequest":
        if not self.model_fields_set:
            raise ValueError("At least one profile field must be provided.")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Profile fields cannot be null.")
        return self


class AssigneeSummary(BaseModel):
    user_id: int
    display_name: str
    tier: str
    skills: list[Category]
    is_available: bool
    active_load: int = Field(ge=0)


class AssigneeListResponse(BaseModel):
    data: list[AssigneeSummary]
    meta: PaginationMeta
