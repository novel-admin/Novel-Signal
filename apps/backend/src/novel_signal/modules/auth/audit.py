"""Security audit events without secrets."""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy.orm import Session

logger = structlog.get_logger("novel_signal.auth.audit")

AUDIT_EVENT_TYPES = frozenset(
    {
        "login",
        "logout",
        "password_change",
        "password_reset_requested",
        "mfa_enrolled",
        "mfa_verified",
        "mfa_removed",
        "auth_failed",
        "authorization_failed",
        "membership_changed",
        "role_changed",
        "membership_removed",
    }
)


def _redacted(extra: dict[str, Any] | None) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    if not extra:
        return safe
    banned = {
        "password",
        "current_password",
        "new_password",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "totp",
        "otp",
        "code",
        "mfa_secret",
        "service_role",
    }
    for key, value in extra.items():
        lowered = key.lower()
        if lowered in banned or "token" in lowered or "secret" in lowered or "password" in lowered:
            safe[key] = "[redacted]"
        else:
            safe[key] = value
    return safe


def audit_event(
    event_type: str,
    *,
    supabase_user_id: str | None = None,
    email: str | None = None,
    workspace_id: str | None = None,
    session: Session | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if event_type not in AUDIT_EVENT_TYPES:
        event_type = "auth_failed"
    record = {
        "audit_event_type": event_type,
        "supabase_user_id": supabase_user_id,
        "email": email,
        "workspace_id": workspace_id,
        "extra": _redacted(extra),
    }
    logger.info("auth_audit", **record)
    if session is not None:
        try:
            from novel_signal.modules.auth.models import AuthAuditEvent

            session.add(
                AuthAuditEvent(
                    event_type=event_type,
                    supabase_user_id=supabase_user_id,
                    email=email,
                    workspace_id=workspace_id,
                )
            )
        except Exception:  # pragma: no cover - audit must never break auth
            logger.warning("auth_audit_persist_failed", event=event_type)
    return record


__all__ = ["AUDIT_EVENT_TYPES", "audit_event"]
