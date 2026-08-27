from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Header, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from novel_signal.api.errors import api_error
from novel_signal.config import get_settings
from novel_signal.db import SessionLocal, get_db
from novel_signal.modules.auth.models import User, Workspace, WorkspaceMember
from novel_signal.modules.auth.service import is_authenticated, token_subject


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


def require_workspace(
    request: Request, session: Annotated[Session, Depends(get_db)]
) -> Workspace:
    """Resolve the first workspace for the authenticated user."""
    from novel_signal.config import get_settings

    settings = get_settings()
    email = token_subject(request.cookies.get(settings.dashboard_auth_cookie))
    if not is_authenticated(
        request.cookies.get(settings.dashboard_auth_cookie), settings
    ) or not email:
        raise api_error(
            "Authentication is required",
            code="AUTH_REQUIRED",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    user = session.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
    workspace = (
        session.scalar(
            select(Workspace)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(WorkspaceMember.user_id == user.id)
            .order_by(Workspace.id)
        )
        if user
        else None
    )
    if workspace is None:
        raise api_error(
            "No workspace membership exists",
            code="WORKSPACE_REQUIRED",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return workspace


WorkspaceDep = Annotated[Workspace, Depends(require_workspace)]


def has_workspace_membership(email: str) -> bool:
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
        if user is None:
            return False
        return session.scalar(
            select(WorkspaceMember.id).where(WorkspaceMember.user_id == user.id).limit(1)
        ) is not None
