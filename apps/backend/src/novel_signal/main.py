from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response

from novel_signal.api.router import api_router
from novel_signal.config import get_settings
from novel_signal.modules.auth.service import is_authenticated


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
allowed_origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def dashboard_access_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    protected_prefix = f"{settings.api_v1_prefix}/"
    public_paths = {
        f"{settings.api_v1_prefix}/health/live",
        f"{settings.api_v1_prefix}/auth/login",
        f"{settings.api_v1_prefix}/auth/session",
        f"{settings.api_v1_prefix}/auth/logout",
    }
    if (
        (
            settings.app_env not in {"development", "test"}
            or settings.dashboard_access_code.get_secret_value()
        )
        and request.url.path.startswith(protected_prefix)
        and request.url.path not in public_paths
        and not is_authenticated(request.cookies.get(settings.dashboard_auth_cookie), settings)
    ):
        return JSONResponse(status_code=401, content={"detail": "Dashboard access required"})
    return await call_next(request)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"name": settings.app_name, "docs": "/docs"}
