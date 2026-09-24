"""Password hashing and JWT helpers shared by authenticated domains."""

import base64
import hashlib
import hmac
import secrets
from datetime import timedelta
from typing import Any

import jwt
from fastapi.security import OAuth2PasswordBearer

from app.core.clock import utc_now

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def decode_access_token(token: str, *, secret: str, algorithm: str) -> dict[str, Any]:
    return jwt.decode(token, secret, algorithms=[algorithm])


def hash_password(password: str) -> str:
    """Hash a password with scrypt and a unique 128-bit salt."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32
    )
    return "scrypt$16384$8$1${}${}".format(
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt_text, digest_text = encoded.split("$", 5)
        if scheme != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def create_access_token(
    *, user_id: int, role: str, secret: str, algorithm: str, expires_minutes: int
) -> tuple[str, int]:
    now = utc_now()
    expires = now + timedelta(minutes=expires_minutes)
    token = jwt.encode(
        {"sub": str(user_id), "role": role, "iat": now, "exp": expires},
        secret,
        algorithm=algorithm,
    )
    return token, expires_minutes * 60
