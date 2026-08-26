from __future__ import annotations

import hmac

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from novel_signal.config import get_settings

from .service import access_token, is_authenticated

router = APIRouter(prefix="/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    code: str


@router.post("/login")
def login(payload: LoginRequest, request: Request) -> JSONResponse:
    settings = get_settings()
    expected = settings.dashboard_access_code.get_secret_value()
    if not expected or not hmac.compare_digest(payload.code, expected):
        return JSONResponse(status_code=401, content={"detail": "Invalid access code"})
    secure = request.url.scheme == "https"
    response = JSONResponse({"authenticated": True})
    response.set_cookie(
        settings.dashboard_auth_cookie,
        access_token(settings),
        httponly=True,
        secure=secure,
        samesite="none" if secure else "lax",
        max_age=60 * 60 * 24 * 7,
    )
    return response


@router.get("/session")
def session(request: Request) -> dict[str, bool]:
    settings = get_settings()
    return {
        "authenticated": not settings.dashboard_access_code.get_secret_value()
        or is_authenticated(request.cookies.get(settings.dashboard_auth_cookie), settings)
    }


@router.post("/logout")
def logout() -> JSONResponse:
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(get_settings().dashboard_auth_cookie)
    return response
