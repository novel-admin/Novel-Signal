import novel_signal.main as main_module
from fastapi.testclient import TestClient
from novel_signal.api.dependencies import has_workspace_membership
from novel_signal.config import Settings, get_settings
from novel_signal.db import Base
from novel_signal.main import app
from novel_signal.modules.auth.models import User, Workspace, WorkspaceMember
from novel_signal.modules.auth.router import PasswordChangeRequest, change_password
from novel_signal.modules.auth.service import (
    access_token,
    is_authenticated,
    password_hash,
    verify_password,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.requests import Request


def test_dashboard_access_is_disabled_without_a_code(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "settings", Settings(dashboard_access_code=""))
    get_settings.cache_clear()
    assert TestClient(app).get("/api/v1/universe/meta").status_code == 200
    get_settings.cache_clear()


def test_dashboard_access_requires_login(monkeypatch) -> None:
    configured = Settings(dashboard_access_code="demo-code", internal_auth_secret="test-secret")
    monkeypatch.setattr(main_module, "settings", configured)
    monkeypatch.setattr("novel_signal.modules.auth.router.get_settings", lambda: configured)
    get_settings.cache_clear()
    client = TestClient(app)
    assert client.get("/api/v1/universe/meta").status_code == 401
    assert client.post("/api/v1/auth/login", json={"code": "wrong"}).status_code == 401
    login = client.post("/api/v1/auth/login", json={"code": "demo-code"})
    assert login.status_code == 200
    assert client.get("/api/v1/auth/session").json() == {
        "authenticated": True,
        "email": "legacy",
    }
    assert client.get("/api/v1/universe/meta").status_code == 200
    get_settings.cache_clear()


def test_dashboard_token_expires(monkeypatch) -> None:
    configured = Settings(internal_auth_secret="test-secret")
    monkeypatch.setattr("novel_signal.modules.auth.service.time", lambda: 1_000_000)
    expired = access_token(
        configured,
        "user@example.com",
        issued_at=1_000_000 - 7 * 24 * 60 * 60 - 1,
    )
    future = access_token(configured, "user@example.com", issued_at=1_000_100)

    assert not is_authenticated(expired, configured)
    assert not is_authenticated(future, configured)


def test_password_change_requires_current_password(monkeypatch) -> None:
    configured = Settings(internal_auth_secret="test-secret")
    monkeypatch.setattr("novel_signal.modules.auth.router.get_settings", lambda: configured)
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(email="user@example.com", password_hash=password_hash("old-password"))
        session.add(user)
        session.commit()
        request = Request(
            {
                "type": "http",
                "headers": [
                    (
                        b"cookie",
                        (
                            f"{configured.dashboard_auth_cookie}="
                            f"{access_token(configured, user.email)}"
                        ).encode(),
                    )
                ],
            }
        )
        result = change_password(
            PasswordChangeRequest(current_password="old-password", new_password="new-password"),
            request,
            session,
        )
        assert result == {"changed": True}
        assert verify_password("new-password", user.password_hash)
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_workspace_membership_is_required_for_authenticated_users(monkeypatch) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        member = User(email="member@example.com", password_hash="hash")
        outsider = User(email="outsider@example.com", password_hash="hash")
        workspace = Workspace(name="Workspace")
        session.add_all([member, outsider, workspace])
        session.flush()
        session.add(WorkspaceMember(user_id=member.id, workspace_id=workspace.id, role="member"))
        session.commit()
    monkeypatch.setattr("novel_signal.api.dependencies.SessionLocal", lambda: Session(engine))

    assert has_workspace_membership("member@example.com")
    assert not has_workspace_membership("outsider@example.com")
    Base.metadata.drop_all(engine)
    engine.dispose()
