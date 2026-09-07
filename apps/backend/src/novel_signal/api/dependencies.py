"""Supabase-first FastAPI dependencies.

Enforcement order for every protected request::

    Supabase JWT -> user identity (sub only, never email)
      -> active workspace membership -> role authorization
      -> resource ownership (workspace_id checked per query)

Internal tool: any valid Supabase session is accepted. There is no
email-verification gate and no MFA/AAL2 requirement.

No workspace ID from the client is trusted without verifying membership.
Frontend auth state is never trusted. Secrets are never logged or returned.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Request, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from novel_signal.api.errors import api_error
from novel_signal.config import get_settings
from novel_signal.db import SessionLocal, get_db
from novel_signal.modules.auth.audit import audit_event
from novel_signal.modules.auth.models import User, Workspace, WorkspaceMember
from novel_signal.modules.auth.roles import Role, meets_requirement, normalize_role
from novel_signal.modules.auth.supabase import (
    SupabaseAuthError,
    SupabaseUser,
    verify_supabase_token,
)


def get_session() -> Generator[Session, None, None]:
    yield from get_db()


def _bearer_token(request: Request) -> str | None:
    auth = request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


def get_supabase_user(request: Request) -> SupabaseUser:
    """Verify the Supabase JWT. Rejects missing/expired/malformed/wrong-project."""
    try:
        return verify_supabase_token(_bearer_token(request))
    except SupabaseAuthError as error:
        audit_event("auth_failed", extra={"code": error.code})
        if error.code == "AUTH_EXPIRED":
            raise api_error(
                "Session has expired",
                code="SESSION_EXPIRED",
                status_code=status.HTTP_401_UNAUTHORIZED,
            ) from error
        raise api_error(
            "Authentication is required",
            code="AUTH_REQUIRED",
            status_code=status.HTTP_401_UNAUTHORIZED,
        ) from error


SupabaseUserDep = Annotated[SupabaseUser, Depends(get_supabase_user)]


def get_app_user(
    user: SupabaseUserDep, session: Annotated[Session, Depends(get_db)]
) -> User:
    """Map Supabase identity to the application profile.

    Identity key is ONLY ``users.supabase_user_id`` (Supabase auth.users.id).
    Email is a display/contact field and is never used as an identity key in
    the request path. Explicit one-time linking for pre-existing development
    profiles happens via the ``link-supabase-user`` CLI, or -- only when
    ``AUTH_ALLOW_EMAIL_FALLBACK_LINKING`` is explicitly enabled for a
    development migration window -- on first verified request. Production
    keeps the fallback disabled. Never creates users.
    """
    profile = session.scalar(select(User).where(User.supabase_user_id == user.sub))
    if profile is None and user.email:
        settings = get_settings()
        if settings.auth_allow_email_fallback_linking:
            by_email = session.scalar(
                select(User).where(
                    User.email == user.email.lower(), User.is_active.is_(True)
                )
            )
            if by_email is not None and by_email.supabase_user_id is None:
                by_email.supabase_user_id = user.sub
                session.commit()
                session.refresh(by_email)
                profile = by_email
                audit_event(
                    "membership_changed",
                    supabase_user_id=user.sub,
                    email=user.email,
                    extra={"reason": "fallback_email_link"},
                )
    if profile is None or not profile.is_active:
        audit_event(
            "authorization_failed",
            supabase_user_id=user.sub,
            email=user.email,
            extra={"reason": "no_profile"},
        )
        raise api_error(
            "Access is not configured for this account",
            code="FORBIDDEN",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return profile


AppUserDep = Annotated[User, Depends(get_app_user)]


class WorkspaceContext:
    def __init__(self, workspace: Workspace, membership: WorkspaceMember, profile: User) -> None:
        self.workspace = workspace
        self.membership = membership
        self.profile = profile

    @property
    def role(self) -> str:
        return normalize_role(self.membership.role) or "viewer"


def require_workspace_membership(
    request: Request, user: SupabaseUserDep, session: Annotated[Session, Depends(get_db)]
) -> WorkspaceContext:
    profile = get_app_user(user, session)
    requested_id = request.headers.get("x-workspace-id") or request.query_params.get("workspace_id")
    membership: WorkspaceMember | None = None
    workspace: Workspace | None = None
    if requested_id:
        # Never trust the client ID: verify membership explicitly.
        membership = session.scalar(
            select(WorkspaceMember)
            .join(User, User.id == WorkspaceMember.user_id)
            .where(
                WorkspaceMember.workspace_id == requested_id,
                WorkspaceMember.user_id == profile.id,
            )
        )
        if membership is None:
            # Avoid revealing whether the workspace exists.
            audit_event(
                "authorization_failed",
                supabase_user_id=user.sub,
                email=user.email,
                extra={"reason": "workspace_forbidden"},
            )
            raise api_error(
                "Access is not configured for this account",
                code="FORBIDDEN",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        workspace = session.get(Workspace, requested_id)
    else:
        membership = session.scalar(
            select(WorkspaceMember)
            .where(WorkspaceMember.user_id == profile.id)
            .order_by(WorkspaceMember.workspace_id)
        )
        workspace = (
            session.get(Workspace, membership.workspace_id) if membership is not None else None
        )
    if membership is None or workspace is None:
        audit_event(
            "authorization_failed",
            supabase_user_id=user.sub,
            email=user.email,
            extra={"reason": "no_membership"},
        )
        raise api_error(
            "Access is not configured for this account",
            code="WORKSPACE_REQUIRED",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    try:
        # Second isolation layer: PostgreSQL RLS policies read this setting.
        session.execute(
            text("SELECT set_config('app.current_workspace_id', :wid, TRUE)"),
            {"wid": str(workspace.id)},
        )
        session.execute(
            text("SELECT set_config('app.current_supabase_user_id', :sid, TRUE)"),
            {"sid": user.sub},
        )
    except Exception:
        # SQLite tests do not support set_config; app-layer checks still apply.
        pass
    return WorkspaceContext(workspace=workspace, membership=membership, profile=profile)


WorkspaceContextDep = Annotated[WorkspaceContext, Depends(require_workspace_membership)]


def require_workspace(
    context: WorkspaceContextDep,
) -> Workspace:
    """Backwards-compatible accessor returning the resolved workspace."""
    return context.workspace


WorkspaceDep = Annotated[Workspace, Depends(require_workspace)]


def require_role(minimum: Role):  # type: ignore[no-untyped-def]
    def _check(context: WorkspaceContextDep) -> WorkspaceContext:
        if not meets_requirement(context.membership.role, minimum):
            audit_event(
                "authorization_failed",
                supabase_user_id=context.profile.supabase_user_id,
                email=context.profile.email,
                workspace_id=str(context.workspace.id),
                extra={"reason": "role_forbidden", "required": minimum},
            )
            raise api_error(
                "Access is not configured for this account",
                code="FORBIDDEN",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        return context

    return _check


def require_internal_access() -> str:
    """Removed: internal header auth is not production authentication."""
    raise api_error(
        "Authentication is required",
        code="AUTH_REQUIRED",
        status_code=status.HTTP_401_UNAUTHORIZED,
    )


def has_workspace_membership(email: str) -> bool:
    """Legacy helper retained for CLI/tests: checks active membership by email."""
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
        if user is None:
            return False
        return (
            session.scalar(
                select(WorkspaceMember.id).where(WorkspaceMember.user_id == user.id).limit(1)
            )
            is not None
        )


def check_resource_workspace(context: WorkspaceContext, resource_workspace_id: object) -> None:
    """Reject cross-workspace access without revealing existence."""
    if resource_workspace_id is None:
        return  # Legacy rows pre-date workspace_id; membership gate applies.
    if str(resource_workspace_id) != str(context.workspace.id):
        audit_event(
            "authorization_failed",
            supabase_user_id=context.profile.supabase_user_id,
            email=context.profile.email,
            workspace_id=str(context.workspace.id),
            extra={"reason": "cross_workspace"},
        )
        raise api_error(
            "Resource was not found",
            code="NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
        )


def _settings_unused() -> None:  # pragma: no cover - keeps import intentional
    get_settings()
