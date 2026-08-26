from __future__ import annotations

import hashlib
import hmac
import secrets
from base64 import urlsafe_b64decode, urlsafe_b64encode
from time import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from novel_signal.config import Settings

from .models import User

TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7


def access_token(settings: Settings, email: str = "", issued_at: int | None = None) -> str:
    secret = settings.internal_auth_secret.get_secret_value().encode()
    subject = email.lower().encode()
    timestamp = str(issued_at if issued_at is not None else int(time()))
    message = f"{urlsafe_b64encode(subject).decode()}.{timestamp}".encode()
    digest = hmac.new(secret, message, hashlib.sha256).hexdigest()
    return f"{message.decode()}.{digest}"


def token_subject(token: str | None) -> str | None:
    if not token or token.count(".") != 2:
        return None
    encoded, _, _ = token.split(".")
    try:
        return urlsafe_b64decode(encoded.encode()).decode()
    except (ValueError, UnicodeDecodeError):
        return None


def is_authenticated(token: str | None, settings: Settings) -> bool:
    if not token or token.count(".") != 2:
        return False
    encoded, timestamp, digest = token.split(".")
    try:
        email = urlsafe_b64decode(encoded.encode()).decode()
        issued_at = int(timestamp)
    except (ValueError, UnicodeDecodeError):
        return False
    if issued_at > int(time()) + 30 or int(time()) - issued_at > TOKEN_TTL_SECONDS:
        return False
    expected = access_token(settings, email, issued_at)
    return hmac.compare_digest(token, expected) and bool(digest)


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
