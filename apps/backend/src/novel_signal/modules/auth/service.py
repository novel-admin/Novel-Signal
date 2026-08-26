from __future__ import annotations

import hashlib
import hmac

from novel_signal.config import Settings


def access_token(settings: Settings) -> str:
    secret = settings.internal_auth_secret.get_secret_value().encode()
    return hmac.new(secret, b"novel-signal-dashboard", hashlib.sha256).hexdigest()


def is_authenticated(token: str | None, settings: Settings) -> bool:
    return bool(token) and hmac.compare_digest(token or "", access_token(settings))
