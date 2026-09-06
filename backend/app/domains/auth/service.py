"""Registration and login business rules."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import UserRole
from app.core.errors import ApplicationError
from app.core.security import create_access_token, hash_password, verify_password
from app.domains.auth.repository import AuthRepository
from app.domains.auth.schema import LoginData, LoginRequest, LoginResponse, RegisterRequest
from app.domains.users.model import User
from app.domains.users.schema import UserResponse
from app.domains.users.service import profile_for


def normalise_email(email: str) -> str:
    return email.strip().lower()


class AuthService:
    def __init__(self, database: Session) -> None:
        self.database = database
        self.repository = AuthRepository(database)

    def register(self, request: RegisterRequest) -> UserResponse:
        email = normalise_email(str(request.email))
        if self.repository.get_by_email(email) is not None:
            raise ApplicationError(
                "EMAIL_ALREADY_REGISTERED", "An account already uses this email.", 409
            )
        user = User(
            email=email,
            password_hash=hash_password(request.password),
            display_name=request.display_name.strip(),
            role_code=UserRole.USER.value,
            is_available=None,
            vendor_org_id=None,
            is_active=True,
        )
        try:
            self.repository.add(user)
            self.database.commit()
        except IntegrityError as exc:
            self.database.rollback()
            raise ApplicationError(
                "EMAIL_ALREADY_REGISTERED", "An account already uses this email.", 409
            ) from exc
        return UserResponse(data=profile_for(user))

    def login(self, request: LoginRequest) -> LoginResponse:
        user = self.repository.get_by_email(normalise_email(str(request.email)))
        if user is None or not user.is_active or not verify_password(
            request.password, user.password_hash
        ):
            raise ApplicationError(
                "INVALID_CREDENTIALS", "The email or password is incorrect.", 401
            )
        settings = get_settings()
        token, expires_in = create_access_token(
            user_id=user.user_id,
            role=user.role_code,
            secret=settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
            expires_minutes=settings.access_token_minutes,
        )
        return LoginResponse(
            data=LoginData(
                access_token=token,
                expires_in=expires_in,
                user=profile_for(user, self.database),
            )
        )
