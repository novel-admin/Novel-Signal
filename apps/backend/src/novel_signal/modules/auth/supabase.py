"""Supabase JWT verification for FastAPI.

Supabase Auth is the only identity provider. The backend never trusts
frontend auth state: every protected request verifies the Supabase JWT,
then enforces workspace membership and roles. There is no
email-verification gate and no MFA/AAL requirement; any valid session is
accepted and the assurance level is informational only.

Supported verification (in order):
1. JWKS (RS256/ES256) from ``SUPABASE_JWKS_URL`` or
   ``{SUPABASE_URL}/auth/v1/.well-known/jwks.json``.
2. HS256 with ``SUPABASE_JWT_SECRET`` (legacy Supabase JWT secret).

Tokens from another Supabase project (wrong ``iss``) are rejected.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient

from novel_signal.config import Settings, get_settings


class SupabaseAuthError(ValueError):
    """Raised when a Supabase JWT cannot be trusted."""

    def __init__(self, code: str, message: str = "Authentication is required") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SupabaseUser:
    sub: str
    email: str | None
    email_verified: bool
    aal: str
    issuer: str | None
    issued_at: int | None
    expires_at: int | None


def _expected_issuer(settings: Settings) -> str | None:
    if settings.supabase_issuer:
        return settings.supabase_issuer
    if settings.supabase_url:
        return f"{settings.supabase_url.rstrip('/')}/auth/v1"
    return None


def _jwks_url(settings: Settings) -> str | None:
    if settings.supabase_jwks_url:
        return settings.supabase_jwks_url
    if settings.supabase_url:
        return f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    return None


@lru_cache(maxsize=4)
def _jwks_client_for_url(url: str) -> PyJWKClient:
    return PyJWKClient(url, timeout=10)


def _aal_from_claims(claims: dict[str, Any]) -> str:
    aal = claims.get("aal")
    if isinstance(aal, str) and aal in {"aal1", "aal2"}:
        return aal
    amr = claims.get("amr")
    if isinstance(amr, list):
        methods = {
            str(entry.get("method")) if isinstance(entry, dict) else str(entry) for entry in amr
        }
        if "totp" in methods or "mfa/totp" in methods or "otp" in methods:
            return "aal2"
    return "aal1"


def _email_verified_from_claims(claims: dict[str, Any]) -> bool:
    for key in ("email_verified", "is_email_verified", "email_confirmed"):
        value = claims.get(key)
        if isinstance(value, bool):
            if value:
                return True
    metadata = claims.get("user_metadata")
    if isinstance(metadata, dict):
        for key in ("email_verified", "email_confirmed", "is_email_verified"):
            if metadata.get(key) is True:
                return True
    # Supabase GoTrue also exposes confirmed_at / email_confirmed_at.
    for key in ("confirmed_at", "email_confirmed_at"):
        if claims.get(key):
            return True
    return False


def _normalize_user(claims: dict[str, Any]) -> SupabaseUser:
    sub = str(claims.get("sub") or "")
    if not sub:
        raise SupabaseAuthError("AUTH_MALFORMED", "Authentication is required")
    email = claims.get("email")
    email_str = str(email).lower() if isinstance(email, str) and email else None
    exp = claims.get("exp")
    iat = claims.get("iat")
    return SupabaseUser(
        sub=sub,
        email=email_str,
        email_verified=_email_verified_from_claims(claims),
        aal=_aal_from_claims(claims),
        issuer=str(claims.get("iss")) if claims.get("iss") else None,
        issued_at=int(iat) if isinstance(iat, (int, float)) else None,
        expires_at=int(exp) if isinstance(exp, (int, float)) else None,
    )


def _check_issuer_and_expiry(
    claims: dict[str, Any], settings: Settings, *, now: int | None = None
) -> None:
    current = now if now is not None else int(time.time())
    exp = claims.get("exp")
    if not isinstance(exp, (int, float)) or int(exp) <= current:
        raise SupabaseAuthError("AUTH_EXPIRED", "Authentication is required")
    expected_issuer = _expected_issuer(settings)
    if expected_issuer and claims.get("iss") != expected_issuer:
        raise SupabaseAuthError("AUTH_WRONG_PROJECT", "Authentication is required")
    aud = claims.get("aud")
    if settings.supabase_audience:
        if isinstance(aud, list):
            if settings.supabase_audience not in [str(item) for item in aud]:
                raise SupabaseAuthError("AUTH_WRONG_PROJECT", "Authentication is required")
        elif isinstance(aud, str):
            if aud not in {"authenticated", settings.supabase_audience}:
                raise SupabaseAuthError("AUTH_WRONG_PROJECT", "Authentication is required")


def verify_supabase_token(token: str | None, settings: Settings | None = None) -> SupabaseUser:
    """Verify a Supabase access token and return the trusted identity."""
    current = settings or get_settings()
    if not token or not token.strip():
        raise SupabaseAuthError("AUTH_REQUIRED", "Authentication is required")
    candidate = token.strip()
    if candidate.lower().startswith("bearer "):
        candidate = candidate[7:].strip()
    if candidate.count(".") != 2:
        raise SupabaseAuthError("AUTH_MALFORMED", "Authentication is required")

    last_error: Exception | None = None
    jwks_url = _jwks_url(current)
    if jwks_url:
        try:
            signing_key = _jwks_client_for_url(jwks_url).get_signing_key_from_jwt(candidate).key
            claims: dict[str, Any] = jwt.decode(
                candidate,
                signing_key,
                algorithms=["RS256", "ES256", "HS256"],
                options={"verify_aud": False, "verify_iss": False},
            )
            _check_issuer_and_expiry(claims, current)
            return _normalize_user(claims)
        except SupabaseAuthError:
            raise
        except Exception as error:  # fall through to HS256 secret
            last_error = error

    jwt_secret = current.supabase_jwt_secret.get_secret_value()
    if jwt_secret:
        try:
            claims = jwt.decode(
                candidate,
                jwt_secret,
                algorithms=["HS256"],
                options={"verify_aud": False, "verify_iss": False},
            )
            _check_issuer_and_expiry(claims, current)
            return _normalize_user(claims)
        except SupabaseAuthError:
            raise
        except jwt.ExpiredSignatureError as error:
            raise SupabaseAuthError("AUTH_EXPIRED", "Authentication is required") from error
        except jwt.InvalidTokenError as error:
            last_error = error
            raise SupabaseAuthError("AUTH_MALFORMED", "Authentication is required") from error

    if last_error is not None and "httpx" in type(last_error).__module__:
        raise SupabaseAuthError("AUTH_UNAVAILABLE", "Authentication is required") from last_error
    raise SupabaseAuthError("AUTH_MALFORMED", "Authentication is required")


def build_test_token(
    claims: dict[str, Any], secret: str = "test-supabase-jwt-secret"
) -> str:
    """Create an HS256 token for tests. Never used in production paths."""
    payload = {"aud": "authenticated", "aal": "aal2", **claims}
    token: str = jwt.encode(payload, secret, algorithm="HS256")
    return token


def clear_jwks_cache() -> None:
    _jwks_client_for_url.cache_clear()


__all__ = [
    "SupabaseAuthError",
    "SupabaseUser",
    "build_test_token",
    "clear_jwks_cache",
    "verify_supabase_token",
]
