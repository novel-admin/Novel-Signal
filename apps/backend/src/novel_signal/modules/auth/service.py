from __future__ import annotations

import hashlib
import hmac
import secrets
from base64 import urlsafe_b64decode, urlsafe_b64encode

from sqlalchemy import select
from sqlalchemy.orm import Session

from novel_signal.config import Settings

from .models import User


def access_token(settings: Settings, email: str = "") -> str:
    secret = settings.internal_auth_secret.get_secret_value().encode()
    subject = email.lower().encode()
    digest = hmac.new(secret, subject, hashlib.sha256).hexdigest()
    return f"{urlsafe_b64encode(subject).decode()}.{digest}"


def is_authenticated(token: str | None, settings: Settings) -> bool:
    if not token or "." not in token:
        return False
    encoded, digest = token.rsplit(".", 1)
    try:
        email = urlsafe_b64decode(encoded.encode()).decode()
    except (ValueError, UnicodeDecodeError):
        return False
    return hmac.compare_digest(token, access_token(settings, email)) and bool(digest)


def password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 240_000)
    salt_text = urlsafe_b64encode(salt).decode()
    derived_text = urlsafe_b64encode(derived).decode()
    return f"pbkdf2_sha256$240000${salt_text}${derived_text}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt, expected = encoded.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), urlsafe_b64decode(salt), int(rounds)
        )
        return hmac.compare_digest(actual, urlsafe_b64decode(expected))
    except (ValueError, TypeError):
        return False


def authenticate(session: Session, email: str, password: str) -> User | None:
    user = session.scalar(
        select(User).where(User.email == email.strip().lower(), User.is_active.is_(True))
    )
    return user if user and verify_password(password, user.password_hash) else None
