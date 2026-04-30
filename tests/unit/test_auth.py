"""
Unit tests for auth.py — password hashing + JWT.
No DB needed — pure function tests.
"""
import pytest
import time
from jose import jwt
from fastapi import HTTPException

from auth import (
    hash_password,
    verify_password,
    create_access_token,
    decode_token,
    get_user_id_from_token,
    CREDENTIALS_EXCEPTION,
    TOKEN_EXPIRED_EXCEPTION,
)
from config import settings


class TestPasswordHashing:
    def test_hash_is_not_plain_text(self):
        plain = "mysecretpassword"
        hashed = hash_password(plain)
        assert hashed != plain

    def test_verify_correct_password(self):
        plain = "mysecretpassword"
        hashed = hash_password(plain)
        assert verify_password(plain, hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("correctpassword")
        assert verify_password("wrongpassword", hashed) is False

    def test_same_password_different_hashes(self):
        """bcrypt uses random salt — same input should produce different hashes."""
        h1 = hash_password("samepassword")
        h2 = hash_password("samepassword")
        assert h1 != h2

    def test_empty_password_hashes(self):
        """Empty string should hash without error (validation is elsewhere)."""
        hashed = hash_password("")
        assert verify_password("", hashed) is True


class TestJWTTokens:
    def test_create_token_returns_string(self):
        token = create_access_token(user_id=1, role="staff", username="worker1")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_valid_token(self):
        token = create_access_token(user_id=42, role="admin", username="boss")
        payload = decode_token(token)
        assert payload["sub"] == "42"
        assert payload["role"] == "admin"
        assert payload["username"] == "boss"

    def test_token_contains_expiry(self):
        token = create_access_token(user_id=1, role="staff", username="test")
        payload = decode_token(token)
        assert "exp" in payload
        assert "iat" in payload

    def test_token_type_is_access(self):
        token = create_access_token(user_id=1, role="staff", username="test")
        payload = decode_token(token)
        assert payload["type"] == "access"

    def test_invalid_token_raises_401(self):
        with pytest.raises(HTTPException) as exc_info:
            decode_token("not.a.real.token")
        assert exc_info.value.status_code == 401

    def test_tampered_token_raises_401(self):
        token = create_access_token(user_id=1, role="staff", username="test")
        tampered = token[:-5] + "XXXXX"
        with pytest.raises(HTTPException) as exc_info:
            decode_token(tampered)
        assert exc_info.value.status_code == 401

    def test_expired_token_raises_401(self):
        """Manually create an expired token."""
        from datetime import datetime, timedelta, timezone
        payload = {
            "sub": "1",
            "role": "staff",
            "username": "test",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
            "iat": datetime.now(timezone.utc) - timedelta(hours=2),
            "type": "access",
        }
        expired_token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        with pytest.raises(HTTPException) as exc_info:
            decode_token(expired_token)
        assert exc_info.value.status_code == 401
        assert "expired" in exc_info.value.detail.lower()

    def test_get_user_id_from_token(self):
        token = create_access_token(user_id=99, role="staff", username="worker")
        user_id = get_user_id_from_token(token)
        assert user_id == 99

    def test_wrong_secret_raises_401(self):
        """Token signed with wrong secret should fail."""
        from datetime import datetime, timedelta, timezone
        payload = {
            "sub": "1", "role": "staff", "username": "test",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "iat": datetime.now(timezone.utc),
            "type": "access",
        }
        fake_token = jwt.encode(payload, "wrong_secret_key", algorithm=settings.ALGORITHM)
        with pytest.raises(HTTPException):
            decode_token(fake_token)
