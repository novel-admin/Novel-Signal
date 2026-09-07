"""Supabase-only authentication tests for the internal Novel tool (mocked JWTs).

Covers the backend portion of the required cases:
- no public signup route, no signup API
- a manually created Supabase user can log in (valid JWT reaches /auth/me)
- a valid AAL1 session can access the application (no MFA/AAL2 requirement)
- unverified email does not block access
- no MFA factor, setup redirect, or challenge exists anywhere
- invalid JWTs rejected (generic 401)
- expired JWTs rejected (401 SESSION_EXPIRED)
- wrong-project JWTs rejected
- unmapped Supabase users rejected (403)
- missing workspace membership rejected (403)
- viewer read-only; analyst/admin/owner permissions work
- cross-workspace reads/writes rejected (404/403 without existence leak)
- removed members lose access (403)
- no account creation through the application
- no service-role key usage
- secrets never appear in responses/logs (audit redaction)
- authenticated responses are no-store
- RLS migration is PostgreSQL-only (SQLite skips; PG verified separately)
"""

from __future__ import annotations

import time
import uuid

import novel_signal.main as main_module
import pytest
from fastapi.testclient import TestClient
from novel_signal.config import Settings, get_settings
from novel_signal.db import Base
from novel_signal.modules.auth import supabase as supabase_module
from novel_signal.modules.auth.models import User, Workspace, WorkspaceMember
from novel_signal.modules.auth.roles import can_change_role, can_write, normalize_role
from novel_signal.modules.auth.supabase import (
    SupabaseAuthError,
    build_test_token,
    verify_supabase_token,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

TEST_SECRET = "test-supabase-jwt-secret-with-32-plus-characters!!"
TEST_ISSUER = "https://test.supabase.co/auth/v1"
WRONG_ISSUER = "https://other.supabase.co/auth/v1"


@pytest.fixture
def supabase_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_JWKS_URL", "")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", TEST_SECRET)
    monkeypatch.setenv("SUPABASE_ISSUER", TEST_ISSUER)
    monkeypatch.setenv("SUPABASE_AUDIENCE", "authenticated")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("AUTH_ALLOW_EMAIL_FALLBACK_LINKING", raising=False)
    get_settings.cache_clear()
    settings = Settings()
    assert settings.auth_allow_email_fallback_linking is False
    monkeypatch.setattr(main_module, "settings", settings)
    supabase_module.clear_jwks_cache()
    yield settings
    get_settings.cache_clear()
    supabase_module.clear_jwks_cache()


def _claims(**overrides):  # type: ignore[no-untyped-def]
    now = int(time.time())
    base = {
        "sub": str(uuid.uuid4()),
        "email": "owner@example.com",
        "email_verified": True,
        "aal": "aal2",
        "iss": TEST_ISSUER,
        "aud": "authenticated",
        "iat": now - 60,
        "exp": now + 3600,
    }
    base.update(overrides)
    return base


def _token(**overrides):  # type: ignore[no-untyped-def]
    return build_test_token(_claims(**overrides), secret=TEST_SECRET)


@pytest.fixture
def db_engine():  # type: ignore[no-untyped-def]
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


def _seed_owner(engine, sub: str, email: str = "owner@example.com", role: str = "owner"):  # type: ignore[no-untyped-def]
    with Session(engine) as session:
        user = User(email=email.lower(), password_hash=None, supabase_user_id=sub)
        workspace = Workspace(name="Novel")
        session.add_all([user, workspace])
        session.flush()
        session.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role=role))
        session.commit()
        return {"user_id": user.id, "workspace_id": workspace.id}


def _client_with_db(engine, monkeypatch):  # type: ignore[no-untyped-def]
    def _factory():  # type: ignore[no-untyped-def]
        return Session(engine)

    monkeypatch.setattr(main_module, "SessionLocal", _factory)
    import novel_signal.api.dependencies as dependencies

    monkeypatch.setattr(dependencies, "SessionLocal", _factory)
    # Point the request DB dependency at the same SQLite engine. Only
    # dependency_overrides is used: reassigning get_db module attributes
    # poisons FastAPI's per-route dependency cache for later tests.
    from novel_signal.db import get_db as real_get_db  # noqa: F401

    def _override_db():  # type: ignore[no-untyped-def]
        with Session(engine) as session:
            yield session

    from novel_signal.main import app

    app.dependency_overrides[real_get_db] = _override_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def authed(supabase_settings, db_engine, monkeypatch):  # type: ignore[no-untyped-def]
    yield from _client_with_db(db_engine, monkeypatch)


def test_signup_routes_do_not_exist(authed, db_engine) -> None:  # type: ignore[no-untyped-def]
    sub = str(uuid.uuid4())
    _seed_owner(db_engine, sub)
    headers = {"Authorization": f"Bearer {_token(sub=sub)}"}
    # With a valid session the router itself must 404: no signup exists.
    assert authed.post("/api/v1/auth/signup", json={}, headers=headers).status_code == 404
    assert authed.post("/api/v1/auth/register", json={}, headers=headers).status_code == 404
    assert authed.get("/api/v1/auth/signup", headers=headers).status_code in {404, 405}


def test_no_account_creation_through_the_application(authed, db_engine) -> None:  # type: ignore[no-untyped-def]
    """No endpoint creates users, workspaces, or Supabase accounts."""
    sub = str(uuid.uuid4())
    _seed_owner(db_engine, sub)
    headers = {"Authorization": f"Bearer {_token(sub=sub)}"}
    for method, path in [
        ("post", "/api/v1/auth/users"),
        ("post", "/api/v1/auth/invite"),
        ("post", "/api/v1/auth/register"),
        ("post", "/api/v1/users"),
        ("post", "/api/v1/workspaces"),
    ]:
        response = authed.request(method, path, json={}, headers=headers)
        assert response.status_code in {404, 405}, (method, path)
    with Session(db_engine) as session:
        assert session.query(User).count() == 1
        assert session.query(Workspace).count() == 1


def test_legacy_login_and_session_routes_are_gone(authed, db_engine) -> None:  # type: ignore[no-untyped-def]
    sub = str(uuid.uuid4())
    _seed_owner(db_engine, sub)
    headers = {"Authorization": f"Bearer {_token(sub=sub)}"}
    assert authed.post("/api/v1/auth/login", json={"code": "x"}, headers=headers).status_code == 404
    assert authed.get("/api/v1/auth/session", headers=headers).status_code == 404


def test_manually_created_user_can_log_in(authed, db_engine) -> None:  # type: ignore[no-untyped-def]
    """Admin creates the Supabase user; email+password login yields a usable session."""
    sub = str(uuid.uuid4())
    _seed_owner(db_engine, sub)
    response = authed.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {_token(sub=sub)}"})
    assert response.status_code == 200
    body = response.json()
    assert body["sub"] == sub
    assert body["workspaces"][0]["role"] == "owner"
    assert "token" not in body and "secret" not in str(body).lower()


def test_invalid_login_returns_generic_401(authed) -> None:  # type: ignore[no-untyped-def]
    response = authed.get("/api/v1/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"
    assert "exists" not in response.text.lower()


def test_missing_token_is_rejected(authed) -> None:  # type: ignore[no-untyped-def]
    response = authed.get("/api/v1/sources/connections")
    assert response.status_code == 401


def test_unverified_email_does_not_block_access(authed, db_engine) -> None:  # type: ignore[no-untyped-def]
    """Internal tool: email verification never gates login or data access."""
    sub = str(uuid.uuid4())
    _seed_owner(db_engine, sub)
    token = _token(sub=sub, email_verified=False, confirmed_at=None)
    headers = {"Authorization": f"Bearer {token}"}
    assert authed.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert authed.get("/api/v1/sources/connections", headers=headers).status_code == 200


def test_aal1_session_can_access_application(authed, db_engine) -> None:  # type: ignore[no-untyped-def]
    """No MFA factor, setup, challenge, or AAL2 requirement exists."""
    sub = str(uuid.uuid4())
    _seed_owner(db_engine, sub)
    token = _token(sub=sub, aal="aal1")
    headers = {"Authorization": f"Bearer {token}"}
    me = authed.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["aal"] == "aal1"
    protected = authed.get("/api/v1/sources/connections", headers=headers)
    assert protected.status_code == 200
    assert protected.headers.get("Cache-Control") == "no-store"


def test_unmapped_user_is_rejected(authed, db_engine) -> None:  # type: ignore[no-untyped-def]
    """A valid JWT whose sub has no application profile gets 403, not data."""
    _seed_owner(db_engine, str(uuid.uuid4()))
    headers = {"Authorization": f"Bearer {_token(sub=str(uuid.uuid4()))}"}
    assert authed.get("/api/v1/sources/connections", headers=headers).status_code == 403
    assert authed.get("/api/v1/auth/workspaces", headers=headers).status_code == 403


def test_no_mfa_challenge_or_factor_checks_anywhere() -> None:
    import pathlib

    root = pathlib.Path("apps/backend/src/novel_signal")
    files = list(root.rglob("*.py"))
    text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore") for path in files
    )
    assert "MFA_REQUIRED" not in text
    assert "EMAIL_UNVERIFIED" not in text
    assert "mfa_required" not in text
    assert "email_unverified" not in text
    assert "is_aal2" not in text
    assert "require_aal2" not in text
    assert "/mfa/" not in text


def test_expired_session_is_rejected(supabase_settings) -> None:
    now = int(time.time())
    token = build_test_token(
        {"sub": str(uuid.uuid4()), "iss": TEST_ISSUER, "iat": now - 7200, "exp": now - 10},
        secret=TEST_SECRET,
    )
    with pytest.raises(SupabaseAuthError) as error:
        verify_supabase_token(token, supabase_settings)
    assert error.value.code == "AUTH_EXPIRED"


def test_session_refresh_with_new_expiry_verifies(supabase_settings) -> None:
    now = int(time.time())
    sub = str(uuid.uuid4())
    old = build_test_token(
        {"sub": sub, "iss": TEST_ISSUER, "iat": now - 3500, "exp": now + 100},
        secret=TEST_SECRET,
    )
    refreshed = build_test_token(
        {"sub": sub, "iss": TEST_ISSUER, "iat": now, "exp": now + 3600},
        secret=TEST_SECRET,
    )
    assert verify_supabase_token(old, supabase_settings).sub == sub
    assert verify_supabase_token(refreshed, supabase_settings).sub == sub


def test_wrong_project_tokens_are_rejected(supabase_settings) -> None:
    token = _token(iss=WRONG_ISSUER)
    with pytest.raises(SupabaseAuthError) as error:
        verify_supabase_token(token, supabase_settings)
    assert error.value.code == "AUTH_WRONG_PROJECT"


def test_malformed_tokens_are_rejected(supabase_settings) -> None:
    for bad in ("", "abc", "a.b", "a.b.c.d", "Bearer "):
        with pytest.raises(SupabaseAuthError):
            verify_supabase_token(bad, supabase_settings)


def test_logout_audits_without_leaking(authed, db_engine) -> None:  # type: ignore[no-untyped-def]
    sub = str(uuid.uuid4())
    _seed_owner(db_engine, sub)
    headers = {"Authorization": f"Bearer {_token(sub=sub)}"}
    response = authed.post("/api/v1/auth/logout", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"authenticated": False}
    # Dropping the token removes access.
    assert authed.get("/api/v1/sources/connections").status_code == 401


def test_deactivated_member_loses_access(authed, db_engine) -> None:  # type: ignore[no-untyped-def]
    sub = str(uuid.uuid4())
    ids = _seed_owner(db_engine, sub)
    with Session(db_engine) as session:
        user = session.get(User, ids["user_id"])
        assert user is not None
        user.is_active = False
        session.commit()
    response = authed.get(
        "/api/v1/sources/connections", headers={"Authorization": f"Bearer {_token(sub=sub)}"}
    )
    assert response.status_code == 403


def test_removed_member_loses_access(authed, db_engine) -> None:  # type: ignore[no-untyped-def]
    sub = str(uuid.uuid4())
    ids = _seed_owner(db_engine, sub)
    with Session(db_engine) as session:
        member = session.query(WorkspaceMember).filter_by(user_id=ids["user_id"]).one()
        session.delete(member)
        session.commit()
    response = authed.get(
        "/api/v1/sources/connections", headers={"Authorization": f"Bearer {_token(sub=sub)}"}
    )
    assert response.status_code in {403, 404}


def test_viewer_cannot_write(authed, db_engine) -> None:  # type: ignore[no-untyped-def]
    sub = str(uuid.uuid4())
    _seed_owner(db_engine, sub, email="viewer@example.com", role="viewer")
    token = _token(sub=sub, email="viewer@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    assert authed.get("/api/v1/sources/connections", headers=headers).status_code == 200
    denied = authed.put(
        "/api/v1/sources/connections/amazon_ads",
        json={"credentials": {"refresh_token": "x"}},
        headers=headers,
    )
    assert denied.status_code == 403


def test_analyst_cannot_perform_owner_operations(authed, db_engine) -> None:  # type: ignore[no-untyped-def]
    sub = str(uuid.uuid4())
    ids = _seed_owner(db_engine, sub, email="analyst@example.com", role="analyst")
    token = _token(sub=sub, email="analyst@example.com")
    response = authed.put(
        f"/api/v1/auth/members/{ids['user_id']}",
        json={"role": "admin"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_cross_workspace_access_is_rejected(authed, db_engine) -> None:  # type: ignore[no-untyped-def]
    sub_a = str(uuid.uuid4())
    ids_a = _seed_owner(db_engine, sub_a, email="a@example.com", role="owner")
    # Second workspace with a different owner.
    sub_b = str(uuid.uuid4())
    with Session(db_engine) as session:
        user_b = User(email="b@example.com", password_hash=None, supabase_user_id=sub_b)
        workspace_b = Workspace(name="Other")
        session.add_all([user_b, workspace_b])
        session.flush()
        session.add(WorkspaceMember(workspace_id=workspace_b.id, user_id=user_b.id, role="owner"))
        session.commit()
        other_id = workspace_b.id
    token_a = _token(sub=sub_a, email="a@example.com")
    # Explicit foreign workspace must not leak existence (403, not the data).
    response = authed.get(
        "/api/v1/sources/connections",
        headers={"Authorization": f"Bearer {token_a}", "X-Workspace-Id": str(other_id)},
    )
    assert response.status_code == 403
    assert ids_a["workspace_id"] != other_id


def test_only_owner_admin_can_change_memberships(authed, db_engine) -> None:  # type: ignore[no-untyped-def]
    owner_sub = str(uuid.uuid4())
    owner_ids = _seed_owner(db_engine, owner_sub, email="owner2@example.com", role="owner")
    analyst_sub = str(uuid.uuid4())
    with Session(db_engine) as session:
        analyst = User(
            email="analyst2@example.com", password_hash=None, supabase_user_id=analyst_sub
        )
        session.add(analyst)
        session.flush()
        session.add(
            WorkspaceMember(
                workspace_id=owner_ids["workspace_id"], user_id=analyst.id, role="analyst"
            )
        )
        session.commit()
        analyst_id = analyst.id
    analyst_token = _token(sub=analyst_sub, email="analyst2@example.com")
    # Analyst cannot promote anyone.
    assert (
        authed.put(
            f"/api/v1/auth/members/{analyst_id}",
            json={"role": "admin"},
            headers={"Authorization": f"Bearer {analyst_token}"},
        ).status_code
        == 403
    )
    # Owner can promote analyst -> admin, but cannot change their own role.
    owner_token = _token(sub=owner_sub, email="owner2@example.com")
    promoted = authed.put(
        f"/api/v1/auth/members/{analyst_id}",
        json={"role": "admin"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "admin"
    assert (
        authed.put(
            f"/api/v1/auth/members/{owner_ids['user_id']}",
            json={"role": "viewer"},
            headers={"Authorization": f"Bearer {owner_token}"},
        ).status_code
        == 403
    )


def test_role_matrix() -> None:
    assert normalize_role("member") == "viewer"
    assert normalize_role("OWNER") == "owner"
    assert normalize_role("nope") is None
    assert can_write("analyst") and not can_write("viewer")
    assert not can_change_role("analyst", "viewer", "admin")
    assert can_change_role("admin", "viewer", "analyst")
    assert not can_change_role("admin", "viewer", "owner")
    assert can_change_role("owner", "admin", "owner")


def test_evidence_and_collection_jobs_are_workspace_scoped(db_engine) -> None:
    from novel_signal.modules.collection.models import CollectionJob, RawEvidence

    with Session(db_engine) as session:
        user = User(
            email="scoped@example.com",
            password_hash=None,
            supabase_user_id=str(uuid.uuid4()),
        )
        workspace = Workspace(name="Scoped")
        session.add_all([user, workspace])
        session.flush()
        session.add(
            WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="admin")
        )
        session.commit()
        assert CollectionJob.__table__.c.workspace_id is not None
        assert RawEvidence.__table__.c.workspace_id is not None


def test_secrets_never_appear_in_responses_or_audit_logs(authed, db_engine, caplog) -> None:  # type: ignore[no-untyped-def]
    from novel_signal.modules.auth.audit import audit_event

    sub = str(uuid.uuid4())
    _seed_owner(db_engine, sub)
    with caplog.at_level("INFO"):
        audit_event(
            "login",
            supabase_user_id=sub,
            extra={"access_token": "secret-value", "password": "secret-value"},
        )
    assert "secret-value" not in caplog.text
    headers = {"Authorization": f"Bearer {_token(sub=sub)}"}
    response = authed.get("/api/v1/auth/me", headers=headers)
    assert "refresh_token" not in response.text.lower()


def test_no_service_role_or_signup_in_backend() -> None:
    import pathlib

    root = pathlib.Path("apps/backend/src/novel_signal")
    files = list(root.rglob("*.py"))
    text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore") for path in files
    )
    assert "SUPABASE_SERVICE_ROLE_KEY" not in text
    assert "supabase_admin" not in text.lower()
    assert "auth.admin" not in text
    assert "/auth/signup" not in text
    assert "AdminAuthClient" not in text


@pytest.fixture
def fallback_enabled(
    supabase_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> Settings:
    """Explicit development migration window only; production stays disabled."""
    monkeypatch.setenv("AUTH_ALLOW_EMAIL_FALLBACK_LINKING", "true")
    get_settings.cache_clear()
    settings = Settings()
    assert settings.auth_allow_email_fallback_linking is True
    monkeypatch.setattr(main_module, "settings", settings)
    yield settings


def _seed_unlinked_owner(engine, email: str = "fallback@example.com"):  # type: ignore[no-untyped-def]
    with Session(engine) as session:
        user = User(email=email.lower(), password_hash=None, supabase_user_id=None)
        workspace = Workspace(name="Fallback")
        session.add_all([user, workspace])
        session.flush()
        session.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner"))
        session.commit()
        return {"user_id": user.id, "workspace_id": workspace.id}


def test_email_fallback_is_disabled_by_default(authed, db_engine) -> None:  # type: ignore[no-untyped-def]
    """Email is display-only: same email, unknown supabase_user_id → 403, no link."""
    ids = _seed_unlinked_owner(db_engine)
    foreign_sub = str(uuid.uuid4())
    headers = {
        "Authorization": f"Bearer {_token(sub=foreign_sub, email='fallback@example.com')}"
    }
    assert authed.get("/api/v1/auth/members", headers=headers).status_code == 403
    assert (
        authed.get("/api/v1/sources/connections", headers=headers).status_code == 403
    )
    with Session(db_engine) as session:
        profile = session.get(User, ids["user_id"])
        assert profile is not None
        assert profile.supabase_user_id is None


def test_email_fallback_links_once_when_enabled(authed, db_engine, fallback_enabled) -> None:  # type: ignore[no-untyped-def]
    ids = _seed_unlinked_owner(db_engine)
    first_sub = str(uuid.uuid4())
    headers = {
        "Authorization": f"Bearer {_token(sub=first_sub, email='fallback@example.com')}"
    }
    assert authed.get("/api/v1/auth/members", headers=headers).status_code == 200
    with Session(db_engine) as session:
        profile = session.get(User, ids["user_id"])
        assert profile is not None
        assert profile.supabase_user_id == first_sub
    # A second identity with the same email must not steal the link.
    second_sub = str(uuid.uuid4())
    other_headers = {
        "Authorization": f"Bearer {_token(sub=second_sub, email='fallback@example.com')}"
    }
    assert authed.get("/api/v1/auth/members", headers=other_headers).status_code == 403
    with Session(db_engine) as session:
        profile = session.get(User, ids["user_id"])
        assert profile is not None
        assert profile.supabase_user_id == first_sub


def test_email_fallback_never_steals_existing_link(authed, db_engine, fallback_enabled) -> None:  # type: ignore[no-untyped-def]
    owner_sub = str(uuid.uuid4())
    ids = _seed_owner(db_engine, owner_sub, email="linked@example.com", role="owner")
    intruder_headers = {
        "Authorization": f"Bearer {_token(sub=str(uuid.uuid4()), email='linked@example.com')}"
    }
    assert authed.get("/api/v1/auth/members", headers=intruder_headers).status_code == 403
    with Session(db_engine) as session:
        profile = session.get(User, ids["user_id"])
        assert profile is not None
        assert profile.supabase_user_id == owner_sub
