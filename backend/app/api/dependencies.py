"""Shared FastAPI dependencies."""

from collections.abc import Generator
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Header
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.common.request_context import RequestContext
from app.core.config import get_settings
from app.core.errors import ApplicationError
from app.core.security import decode_access_token, oauth2_scheme
from app.db.session import SessionLocal


def get_db() -> Generator[Session, None, None]:
    database = SessionLocal()
    try:
        yield database
    finally:
        database.close()


def request_id_header(
    x_request_id: Annotated[UUID | None, Header(alias="X-Request-ID")] = None,
) -> UUID | None:
    return x_request_id


def get_current_actor(
    token: Annotated[str, Depends(oauth2_scheme)],
    database: Annotated[Session, Depends(get_db)],
) -> RequestContext:
    settings = get_settings()
    try:
        claims = decode_access_token(
            token,
            secret=settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
        )
        raw_subject = claims.get("sub", claims.get("user_id"))
        user_id = int(raw_subject)
    except (jwt.PyJWTError, TypeError, ValueError):
        raise ApplicationError(
            "INVALID_ACCESS_TOKEN",
            "The access token is invalid or expired.",
            401,
        ) from None

    row = database.execute(
        text(
            """
            SELECT user_id, role_code, vendor_org_id
            FROM users
            WHERE user_id = :user_id AND is_active = 1
            """
        ),
        {"user_id": user_id},
    ).mappings().one_or_none()
    if row is None:
        raise ApplicationError(
            "INVALID_ACCESS_TOKEN",
            "The access token is invalid or expired.",
            401,
        )
    return RequestContext(
        user_id=int(row["user_id"]),
        role=str(row["role_code"]),
        vendor_org_id=(
            int(row["vendor_org_id"]) if row["vendor_org_id"] is not None else None
        ),
    )
