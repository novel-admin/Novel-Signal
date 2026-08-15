from collections.abc import Generator

from fastapi import Header, status
from sqlalchemy.orm import Session

from novel_signal.api.errors import api_error
from novel_signal.config import get_settings
from novel_signal.db import get_db


def get_session() -> Generator[Session, None, None]:
    yield from get_db()


def require_internal_access(x_internal_token: str | None = Header(default=None)) -> str:
    """Week 1 access gate; replace with application auth without changing routes."""
    settings = get_settings()
    expected = settings.internal_auth_secret.get_secret_value()
    if not x_internal_token or x_internal_token != expected:
        raise api_error(
            "Internal access is required",
            code="AUTH_REQUIRED",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    return "internal-admin"
