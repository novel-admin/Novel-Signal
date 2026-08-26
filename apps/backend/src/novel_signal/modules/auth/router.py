from __future__ import annotations

# ruff: noqa: B008
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from novel_signal.config import get_settings
from novel_signal.db import get_db

from .service import access_token, authenticate, is_authenticated

router = APIRouter(prefix="/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    email: str = ""
    password: str = ""
    code: str = ""


@router.post("/login")
def login(
    payload: LoginRequest, request: Request, session: Session = Depends(get_db)
) -> JSONResponse:
    settings = get_settings()
    login_email = ""
    if payload.code:
        expected = settings.dashboard_access_code.get_secret_value()
        if expected and payload.code == expected:
            login_email = "legacy"
    elif payload.email:
        user = authenticate(session, payload.email, payload.password)
        login_email = user.email if user else ""
    if not login_email:
        return JSONResponse(status_code=401, content={"detail": "Invalid email or password"})
    # Render terminates TLS before forwarding to the app.  Use the deployment
    # environment as the source of truth so the browser does not silently
    # reject the cross-origin session cookie when proxy headers are absent.
    secure = request.url.scheme == "https" or settings.app_env not in {"development", "test"}
    response = JSONResponse({"authenticated": True, "token": access_token(settings, login_email)})
    response.set_cookie(
        settings.dashboard_auth_cookie,
        access_token(settings, login_email),
        httponly=True,
        secure=secure,
        samesite="none" if secure else "lax",
        path="/",
        max_age=60 * 60 * 24 * 7,
    )
    return response


@router.get("/session")
def session(request: Request) -> dict[str, bool | str | None]:
    settings = get_settings()
    token = request.cookies.get(settings.dashboard_auth_cookie)
    authenticated = is_authenticated(token, settings)
    return {
        "authenticated": authenticated,
        "email": None,
    }


@router.post("/logout")
def logout() -> JSONResponse:
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(get_settings().dashboard_auth_cookie)
    return response
