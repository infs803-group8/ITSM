"""auth API routes.

Implement operations exactly from backend/contracts/openapi.yaml.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.common.responses import ErrorResponse
from app.domains.auth.schema import LoginRequest, LoginResponse, RegisterRequest
from app.domains.auth.service import AuthService
from app.domains.users.schema import UserResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="api08Register",
    summary="Register requester account",
    responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def register(
    request: RegisterRequest, database: Annotated[Session, Depends(get_db)]
) -> UserResponse:
    return AuthService(database).register(request)


@router.post(
    "/login",
    response_model=LoginResponse,
    operation_id="api09Login",
    summary="Login and obtain JWT",
    responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def login(
    request: LoginRequest, database: Annotated[Session, Depends(get_db)]
) -> LoginResponse:
    return AuthService(database).login(request)
