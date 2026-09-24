from datetime import UTC, datetime, timedelta

import jwt

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_is_salted_and_verifiable():
    first = hash_password("ExamplePass123!")
    second = hash_password("ExamplePass123!")

    assert first != second
    assert "ExamplePass123!" not in first
    assert verify_password("ExamplePass123!", first)
    assert not verify_password("wrong-password", first)


def test_access_token_contains_contract_identity_and_expiry():
    token, expires_in = create_access_token(
        user_id=42,
        role="USER",
        secret="test-secret-that-is-at-least-32-bytes",
        algorithm="HS256",
        expires_minutes=60,
    )
    claims = decode_access_token(
        token, secret="test-secret-that-is-at-least-32-bytes", algorithm="HS256"
    )

    assert claims["sub"] == "42"
    assert claims["role"] == "USER"
    assert expires_in == 3600
    assert datetime.fromtimestamp(claims["exp"], UTC) > datetime.now(UTC) + timedelta(
        minutes=59
    )


def test_access_token_rejects_wrong_secret():
    token, _ = create_access_token(
        user_id=42,
        role="USER",
        secret="correct-secret-that-is-at-least-32-bytes",
        algorithm="HS256",
        expires_minutes=60,
    )

    try:
        decode_access_token(
            token, secret="wrong-secret-that-is-at-least-32-bytes", algorithm="HS256"
        )
    except jwt.InvalidSignatureError:
        pass
    else:
        raise AssertionError("Token signed by another secret must be rejected")
