"""API-19 and API-20 request and response schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.common.pagination import PaginationMeta
from app.core.enums import CommentVisibility, UserRole


class ActorSummary(BaseModel):
    user_id: int
    display_name: str
    role: UserRole


class CommentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)
    visibility: CommentVisibility

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be blank")
        return value


class CommentView(BaseModel):
    comment_id: int
    ticket_id: int
    author: ActorSummary
    message: str
    visibility: CommentVisibility
    created_at: datetime


class CommentResponse(BaseModel):
    data: CommentView


class CommentListResponse(BaseModel):
    data: list[CommentView]
    meta: PaginationMeta
