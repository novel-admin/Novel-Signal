"""Supabase-only identity endpoints for the internal Novel tool.

No public signup, no account provisioning, no invitations, no Admin API,
and no service-role key usage exist in this application. The platform
administrator creates every login email and password manually in the
Supabase Dashboard; workspace membership/role is assigned separately
through the approved owner/admin flow (membership endpoints below or CLI).

Login, session refresh, and password reset/change all happen via Supabase
Auth (frontend). The backend only verifies Supabase JWTs and enforces
application mapping, workspace membership, and roles. There is no MFA,
no AAL2 requirement, and no email-verification gate: any valid Supabase
session is accepted.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from novel_signal.api.errors import api_error
from novel_signal.db import get_db
from novel_signal.modules.auth.audit import audit_event
from novel_signal.modules.auth.models import User, Workspace, WorkspaceMember
from novel_signal.modules.auth.roles import Role, can_change_role, normalize_role
from novel_signal.modules.auth.supabase import (
    SupabaseAuthError,
    SupabaseUser,
    verify_supabase_token,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


class WorkspaceRoleRead(BaseModel):
    id: str
    name: str
    role: str


class MeResponse(BaseModel):
    sub: str
    email: str | None
    email_verified: bool
    aal: str
    workspaces: list[WorkspaceRoleRead]


class MemberRead(BaseModel):
    user_id: str
    email: str | None
    role: str
    supabase_user_id: str | None = None


class MemberRoleUpdate(BaseModel):
    role: Role


def _bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


def _authenticated_identity(request: Request) -> SupabaseUser:
    """Valid Supabase session. No email or MFA checks: internal tool login
    accepts any valid session; mapping and membership are enforced next."""
    try:
        return verify_supabase_token(_bearer(request))
    except SupabaseAuthError as error:
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


def _workspaces_for_profile(session: Session, profile: User) -> list[WorkspaceRoleRead]:
    rows = session.execute(
        select(Workspace, WorkspaceMember)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == profile.id)
        .order_by(Workspace.id)
    ).all()
    result: list[WorkspaceRoleRead] = []
    for workspace, membership in rows:
        role = normalize_role(membership.role) or "viewer"
        result.append(WorkspaceRoleRead(id=str(workspace.id), name=workspace.name, role=role))
    return result


def _profile_for_user(session: Session, user: SupabaseUser) -> User | None:
    """Provision a Supabase Dashboard user into Novel's fixed tenant."""
    profile = session.scalar(select(User).where(User.supabase_user_id == user.sub))
    if profile is None and user.email:
        profile = User(email=user.email.lower(), supabase_user_id=user.sub, is_active=True)
        session.add(profile)
        session.flush()
    if profile is not None:
        workspace = session.scalar(select(Workspace).where(Workspace.name == "Novel"))
        if workspace is None:
            workspace = Workspace(name="Novel")
            session.add(workspace)
            session.flush()
        membership = session.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace.id,
                WorkspaceMember.user_id == profile.id,
            )
        )
        if membership is None:
            session.add(
                WorkspaceMember(workspace_id=workspace.id, user_id=profile.id, role="viewer")
            )
    if profile is not None and not profile.is_active:
        return None
    return profile


@router.get("/me", response_model=MeResponse)
def me(request: Request, session: Annotated[Session, Depends(get_db)]) -> MeResponse:
    user = _authenticated_identity(request)
    profile = _profile_for_user(session, user)
    workspaces = _workspaces_for_profile(session, profile) if profile is not None else []
    return MeResponse(
        sub=user.sub,
        email=user.email,
        email_verified=user.email_verified,
        aal=user.aal,
        workspaces=workspaces,
    )


@router.get("/workspaces", response_model=list[WorkspaceRoleRead])
def list_my_workspaces(
    request: Request, session: Annotated[Session, Depends(get_db)]
) -> list[WorkspaceRoleRead]:
    user = _authenticated_identity(request)
    profile = _profile_for_user(session, user)
    if profile is None:
        raise api_error(
            "Access is not configured for this account",
            code="FORBIDDEN",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return _workspaces_for_profile(session, profile)


def _require_workspace_owner_admin(
    request: Request, session: Session
) -> tuple[SupabaseUser, User, Workspace, WorkspaceMember]:
    from novel_signal.api.dependencies import require_workspace_membership
    from novel_signal.modules.auth.roles import meets_requirement

    # Reuse the full chain: JWT -> membership.
    try:
        user = verify_supabase_token(_bearer(request))
    except SupabaseAuthError as error:
        raise api_error(
            "Authentication is required",
            code="AUTH_REQUIRED",
            status_code=status.HTTP_401_UNAUTHORIZED,
        ) from error
    context = require_workspace_membership(request, user, session)
    if not meets_requirement(context.membership.role, "admin"):
        audit_event(
            "authorization_failed",
            supabase_user_id=user.sub,
            email=user.email,
            workspace_id=str(context.workspace.id),
            extra={"reason": "members_admin_required"},
        )
        raise api_error(
            "Access is not configured for this account",
            code="FORBIDDEN",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return user, context.profile, context.workspace, context.membership


@router.get("/members", response_model=list[MemberRead])
def list_members(
    request: Request, session: Annotated[Session, Depends(get_db)]
) -> list[MemberRead]:
    _, _, workspace, _ = _require_workspace_owner_admin(request, session)
    rows = session.execute(
        select(User, WorkspaceMember)
        .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
        .where(WorkspaceMember.workspace_id == workspace.id)
        .order_by(User.email)
    ).all()
    return [
        MemberRead(
            user_id=str(profile.id),
            email=profile.email,
            role=normalize_role(membership.role) or "viewer",
            supabase_user_id=profile.supabase_user_id,
        )
        for profile, membership in rows
    ]


@router.put("/members/{user_id}", response_model=MemberRead)
def update_member_role(
    user_id: str,
    payload: MemberRoleUpdate,
    request: Request,
    session: Annotated[Session, Depends(get_db)],
) -> MemberRead:
    actor, actor_profile, workspace, actor_membership = _require_workspace_owner_admin(
        request, session
    )
    target_membership = session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == user_id,
        )
    )
    if target_membership is None:
        # Do not reveal whether the user exists.
        raise api_error("Resource was not found", code="NOT_FOUND", status_code=404)
    if target_membership.user_id == actor_profile.id:
        raise api_error(
            "You cannot change your own role",
            code="FORBIDDEN",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    target_profile = session.get(User, user_id)
    current_role = normalize_role(target_membership.role) or "viewer"
    if not can_change_role(actor_membership.role, current_role, payload.role):
        audit_event(
            "authorization_failed",
            supabase_user_id=actor.sub,
            email=actor.email,
            workspace_id=str(workspace.id),
            extra={"reason": "role_change_forbidden"},
        )
        raise api_error(
            "Access is not configured for this account",
            code="FORBIDDEN",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    target_membership.role = payload.role
    session.commit()
    audit_event(
        "role_changed",
        supabase_user_id=actor.sub,
        email=actor.email,
        workspace_id=str(workspace.id),
        extra={"target_user_id": user_id, "new_role": payload.role},
        session=session,
    )
    try:
        session.commit()
    except Exception:
        session.rollback()
    return MemberRead(
        user_id=str(target_profile.id) if target_profile else user_id,
        email=target_profile.email if target_profile else None,
        role=payload.role,
        supabase_user_id=target_profile.supabase_user_id if target_profile else None,
    )


@router.delete("/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    user_id: str, request: Request, session: Annotated[Session, Depends(get_db)]
) -> None:
    actor, actor_profile, workspace, _ = _require_workspace_owner_admin(request, session)
    if user_id == actor_profile.id:
        raise api_error(
            "You cannot remove your own membership",
            code="FORBIDDEN",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    target = session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == user_id,
        )
    )
    if target is None:
        raise api_error("Resource was not found", code="NOT_FOUND", status_code=404)
    session.delete(target)
    session.commit()
    audit_event(
        "membership_removed",
        supabase_user_id=actor.sub,
        email=actor.email,
        workspace_id=str(workspace.id),
        extra={"target_user_id": user_id},
        session=session,
    )
    try:
        session.commit()
    except Exception:
        session.rollback()
    return None


@router.post("/logout")
def logout(request: Request) -> dict[str, bool]:
    try:
        user = verify_supabase_token(_bearer(request))
        audit_event("logout", supabase_user_id=user.sub, email=user.email)
    except SupabaseAuthError:
        pass
    return {"authenticated": False}
