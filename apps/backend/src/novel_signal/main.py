from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from starlette.responses import Response

from novel_signal.api.router import api_router
from novel_signal.config import get_settings
from novel_signal.db import SessionLocal
from novel_signal.modules.auth.audit import audit_event
from novel_signal.modules.auth.models import User, WorkspaceMember
from novel_signal.modules.auth.roles import can_write
from novel_signal.modules.auth.supabase import SupabaseAuthError, verify_supabase_token
from novel_signal.scheduler import start_scheduler, stop_scheduler
from novel_signal.tenant import tenant_scope


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    scheduler = None
    if settings.internal_scheduler_enabled and settings.app_env != "test":
        scheduler = start_scheduler(settings)
    try:
        yield
    finally:
        if scheduler is not None:
            await stop_scheduler(*scheduler)


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
allowed_origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Workspace-Id"],
    max_age=600,
)


def _generic_401(code: str) -> JSONResponse:
    if code == "SESSION_EXPIRED":
        return JSONResponse(
            status_code=401, content={"code": code, "message": "Session has expired"}
        )
    return JSONResponse(
        status_code=401, content={"code": "AUTH_REQUIRED", "message": "Authentication is required"}
    )


def _supabase_configured() -> bool:
    return bool(
        settings.supabase_url.strip()
        or settings.supabase_jwks_url.strip()
        or settings.supabase_jwt_secret.get_secret_value().strip()
    )


@app.middleware("http")
async def supabase_auth_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    protected_prefix = f"{settings.api_v1_prefix}/"
    public_paths = {
        f"{settings.api_v1_prefix}/health/live",
        f"{settings.api_v1_prefix}/health/ready",
    }
    # Identity endpoints are reachable with any valid session so the
    # frontend can distinguish missing mapping/membership from expiry.
    # Everything else under /api/v1 requires a mapped user + membership.
    # Internal tool: no email-verification gate and no MFA/AAL2 requirement;
    # any valid Supabase session (AAL1 or AAL2) is accepted.
    identity_paths = {
        f"{settings.api_v1_prefix}/auth/me",
        f"{settings.api_v1_prefix}/auth/workspaces",
    }
    path = request.url.path
    if request.method == "OPTIONS" or not path.startswith(protected_prefix):
        return await call_next(request)
    if path in public_paths:
        return await call_next(request)
    # When Supabase is not configured (local dev / legacy test fixtures),
    # allow requests through so existing domain tests keep exercising business
    # logic. Production fails closed when identity is not configured.
    if not _supabase_configured():
        if settings.app_env == "production":
            return JSONResponse(
                status_code=503,
                content={"code": "UNAVAILABLE", "message": "Service is temporarily unavailable"},
            )
        return await call_next(request)

    auth_header = request.headers.get("authorization")
    token: str | None = None
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip() or None
    try:
        supabase_user = verify_supabase_token(token)
    except SupabaseAuthError as error:
        audit_event("auth_failed", extra={"code": error.code})
        return _generic_401(error.code)
    # Internal tool: email verification is not enforced here and there is
    # no MFA/AAL2 requirement. Any valid Supabase session is accepted;
    # membership and roles are enforced below.
    if path in identity_paths:
        request.state.supabase_user = supabase_user
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response
    # Active membership is required before any application data.
    # Identity key is ONLY users.supabase_user_id. Email is display-only.
    # The resolved workspace becomes the request tenant scope: the ORM layer
    # auto-filters every tenant-owned query and PostgreSQL RLS enforces it.
    resolved_workspace_id: str | None = None
    try:
        with SessionLocal() as session:
            profile = session.scalar(
                select(User).where(User.supabase_user_id == supabase_user.sub)
            )
            if profile is None and settings.auth_allow_email_fallback_linking:
                # Development migration window only. Production keeps this
                # disabled: email is display-only, never an identity key.
                candidate = (
                    session.scalar(
                        select(User).where(
                            User.email == (supabase_user.email or "").lower(),
                            User.is_active.is_(True),
                        )
                    )
                    if supabase_user.email
                    else None
                )
                if candidate is not None and candidate.supabase_user_id is None:
                    candidate.supabase_user_id = supabase_user.sub
                    session.commit()
                    session.refresh(candidate)
                    audit_event(
                        "membership_changed",
                        supabase_user_id=supabase_user.sub,
                        email=supabase_user.email,
                        extra={"reason": "fallback_email_link"},
                    )
                    profile = candidate
            if profile is None or not profile.is_active:
                audit_event(
                    "authorization_failed",
                    supabase_user_id=supabase_user.sub,
                    email=supabase_user.email,
                    extra={"reason": "no_membership"},
                )
                return JSONResponse(
                    status_code=403,
                    content={
                        "code": "FORBIDDEN",
                        "message": "Access is not configured for this account",
                    },
                )
            memberships = list(
                session.scalars(
                    select(WorkspaceMember)
                    .where(WorkspaceMember.user_id == profile.id)
                    .order_by(WorkspaceMember.workspace_id)
                ).all()
            )
            if not memberships:
                audit_event(
                    "authorization_failed",
                    supabase_user_id=supabase_user.sub,
                    email=supabase_user.email,
                    extra={"reason": "no_membership"},
                )
                return JSONResponse(
                    status_code=403,
                    content={
                        "code": "WORKSPACE_REQUIRED",
                        "message": "Access is not configured for this account",
                    },
                )
            requested_id = request.headers.get("x-workspace-id") or request.query_params.get(
                "workspace_id"
            )
            if requested_id:
                # Never trust the client ID without verifying membership, and
                # never reveal whether the workspace exists.
                if not any(str(member.workspace_id) == requested_id for member in memberships):
                    audit_event(
                        "authorization_failed",
                        supabase_user_id=supabase_user.sub,
                        email=supabase_user.email,
                        extra={"reason": "workspace_forbidden"},
                    )
                    return JSONResponse(
                        status_code=403,
                        content={
                            "code": "FORBIDDEN",
                            "message": "Access is not configured for this account",
                        },
                    )
                resolved_workspace_id = requested_id
            else:
                resolved_workspace_id = str(memberships[0].workspace_id)
            if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not any(
                can_write(member.role) for member in memberships
            ):
                audit_event(
                    "authorization_failed",
                    supabase_user_id=supabase_user.sub,
                    email=supabase_user.email,
                    extra={"reason": "viewer_write_blocked"},
                )
                return JSONResponse(
                    status_code=403,
                    content={
                        "code": "FORBIDDEN",
                        "message": "Access is not configured for this account",
                    },
                )
    except Exception:
        # If the database is unavailable, fail closed without leaking details.
        return JSONResponse(
            status_code=503,
            content={"code": "UNAVAILABLE", "message": "Service is temporarily unavailable"},
        )
    request.state.supabase_user = supabase_user
    with tenant_scope(resolved_workspace_id, supabase_user.sub):
        response = await call_next(request)
    # Never cache authenticated responses across users.
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return response


app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"name": settings.app_name, "docs": "/docs"}
