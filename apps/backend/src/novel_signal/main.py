from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from starlette.responses import Response

from novel_signal.api.router import api_router
from novel_signal.config import Settings, get_settings
from novel_signal.db import SessionLocal
from novel_signal.modules.auth.audit import audit_event
from novel_signal.modules.auth.models import Workspace
from novel_signal.modules.auth.supabase import SupabaseAuthError, verify_supabase_token
from novel_signal.scheduler import start_scheduler, stop_scheduler
from novel_signal.tenant import tenant_scope


def _generic_401(code: str) -> JSONResponse:
    if code == "SESSION_EXPIRED":
        return JSONResponse(
            status_code=401, content={"code": code, "message": "Session has expired"}
        )
    return JSONResponse(
        status_code=401, content={"code": "AUTH_REQUIRED", "message": "Authentication is required"}
    )


def _supabase_configured(settings: Settings) -> bool:
    return bool(
        settings.supabase_url.strip()
        or settings.supabase_jwks_url.strip()
        or settings.supabase_jwt_secret.get_secret_value().strip()
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    use_module_settings = settings is None

    def current_settings() -> Settings:
        if use_module_settings:
            return cast(Settings, globals()["settings"])
        return app_settings

    @asynccontextmanager
    async def app_lifespan(_: FastAPI) -> AsyncIterator[None]:
        scheduler = None
        if app_settings.internal_scheduler_enabled and app_settings.app_env != "test":
            scheduler = start_scheduler(app_settings)
        try:
            yield
        finally:
            if scheduler is not None:
                await stop_scheduler(*scheduler)

    app = FastAPI(
        title=app_settings.app_name, version="0.1.0", lifespan=app_lifespan
    )

    @app.middleware("http")
    async def supabase_auth_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_settings = current_settings()
        protected_prefix = f"{request_settings.api_v1_prefix}/"
        public_paths = {
            f"{request_settings.api_v1_prefix}/health/live",
            f"{request_settings.api_v1_prefix}/health/ready",
        }
        identity_paths = {
            f"{request_settings.api_v1_prefix}/auth/me",
            f"{request_settings.api_v1_prefix}/auth/workspaces",
        }
        path = request.url.path
        if request.method == "OPTIONS" or not path.startswith(protected_prefix):
            return await call_next(request)
        if path in public_paths:
            return await call_next(request)
        if not _supabase_configured(request_settings):
            if request_settings.app_env == "production":
                return JSONResponse(
                    status_code=503,
                    content={
                        "code": "UNAVAILABLE",
                        "message": "Service is temporarily unavailable",
                    },
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
        if path in identity_paths:
            request.state.supabase_user = supabase_user
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            return response
        try:
            with SessionLocal() as session:
                workspace = session.scalar(select(Workspace).where(Workspace.name == "Novel"))
                if workspace is None:
                    workspace = Workspace(name="Novel")
                    session.add(workspace)
                    session.flush()
                resolved_workspace_id = str(workspace.id)
        except Exception:
            return JSONResponse(
                status_code=503,
                content={"code": "UNAVAILABLE", "message": "Service is temporarily unavailable"},
            )
        request.state.supabase_user = supabase_user
        with tenant_scope(resolved_workspace_id, supabase_user.sub):
            response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        return response

    app.include_router(api_router, prefix=app_settings.api_v1_prefix)

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"name": app_settings.app_name, "docs": "/docs"}

    allowed_origins = [
        origin.strip() for origin in app_settings.allowed_origins.split(",") if origin.strip()
    ]
    # Added last so CORS wraps auth middleware, including its early error responses.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Range", "X-Total-Count", "X-Page", "X-Page-Size"],
        max_age=600,
    )
    return app


settings = get_settings()
app = create_app()
