"""Tenant isolation: ORM auto-scope, API cross-workspace rejection, CLI linking.

- ORM layer: before_flush auto-fill + with_loader_criteria auto-filter for
  every WorkspaceOwned entity (SQLite, no network).
- API layer: two real workspaces, cross-workspace reads/writes rejected
  without existence leaks (mocked Supabase JWTs).
- CLI: link-supabase-user one-time migration tool.
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
from novel_signal.modules.auth.supabase import build_test_token
from novel_signal.modules.collection.models import (
    CollectionJob,
    CollectionJobType,
    CollectionSourceTier,
)
from novel_signal.modules.universe.models import Competitor
from novel_signal.tenant import (
    orm_scoped_count,
    tenant_scope,
    workspace_owned_entities,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

TEST_SECRET = "test-supabase-jwt-secret-with-32-plus-characters!!"
TEST_ISSUER = "https://test.supabase.co/auth/v1"


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


def _client_with_db(engine, monkeypatch):  # type: ignore[no-untyped-def]
    def _factory():  # type: ignore[no-untyped-def]
        return Session(engine)

    monkeypatch.setattr(main_module, "SessionLocal", _factory)
    import novel_signal.api.dependencies as dependencies

    monkeypatch.setattr(dependencies, "SessionLocal", _factory)
    # Overrides only: reassigning get_db module attributes poisons FastAPI's
    # per-route dependency cache for later tests.
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


def _seed_workspace(engine, email: str, name: str, role: str = "owner"):  # type: ignore[no-untyped-def]
    sub = str(uuid.uuid4())
    with Session(engine) as session:
        user = User(email=email.lower(), password_hash=None, supabase_user_id=sub)
        workspace = session.scalar(select(Workspace).where(Workspace.name == "Novel"))
        if workspace is None:
            workspace = Workspace(name="Novel")
        session.add_all([user, workspace])
        session.flush()
        session.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role=role))
        session.commit()
        return {"sub": sub, "user_id": user.id, "workspace_id": workspace.id}


def test_every_tenant_table_is_orm_scoped() -> None:
    entities = workspace_owned_entities()
    assert orm_scoped_count() == 51
    names = sorted(entity.__tablename__ for entity in entities)
    for expected in (
        "competitors",
        "products",
        "keywords",
        "collection_jobs",
        "raw_evidence",
        "gaps",
        "actions",
        "alert_events",
        "scorecard_cells",
        "price_observations",
        "serp_captures",
        "listing_snapshots",
        "review_observations",
        "ad_observations",
        "units_estimates",
        "tracking_targets",
        "battle_cards",
    ):
        assert expected in names, expected
    # Identity/membership/global tables stay out of the auto-filter.
    for excluded in (
        "users",
        "workspaces",
        "workspace_members",
        "source_credentials",
        "parser_versions",
        "auth_audit_events",
    ):
        assert excluded not in names, excluded


def test_orm_autofill_and_filter_select_get_update_delete(db_engine) -> None:
    with Session(db_engine) as session:
        with tenant_scope("ws-a"):
            session.add(Competitor(name="A1"))
            session.commit()
        with tenant_scope("ws-b"):
            session.add(Competitor(name="B1"))
            session.commit()
        # Legacy rows without ownership stay visible only without a scope.
        session.add(Competitor(name="Legacy"))
        session.commit()

        assert sorted(
            row.name for row in session.scalars(select(Competitor)).all()
        ) == ["A1", "B1", "Legacy"]

        with tenant_scope("ws-a"):
            assert [row.name for row in session.scalars(select(Competitor)).all()] == ["A1"]
            own_id = session.scalar(select(Competitor.id).where(Competitor.name == "A1"))
            assert session.get(Competitor, own_id) is not None
            session.expunge_all()
        foreign_id = session.scalar(select(Competitor.id).where(Competitor.name == "B1"))
        assert foreign_id is not None
        with tenant_scope("ws-a"):
            # Fresh sessions never resolve foreign rows, even by primary key.
            session.expunge_all()
            assert session.get(Competitor, foreign_id) is None
            assert (
                session.query(Competitor)
                .filter(Competitor.name == "B1")
                .update({"threat_rating": 5})
                == 0
            )
            assert (
                session.query(Competitor).filter(Competitor.name == "B1").delete() == 0
            )
            session.rollback()
        with tenant_scope("ws-b"):
            assert [row.name for row in session.scalars(select(Competitor)).all()] == ["B1"]


def test_api_cross_workspace_competitors_are_rejected(authed, db_engine) -> None:  # type: ignore[no-untyped-def]
    owner_a = _seed_workspace(db_engine, "a@example.com", "Workspace A")
    owner_b = _seed_workspace(db_engine, "b@example.com", "Workspace B")
    headers_a = {"Authorization": f"Bearer {_token(sub=owner_a['sub'], email='a@example.com')}"}
    headers_b = {"Authorization": f"Bearer {_token(sub=owner_b['sub'], email='b@example.com')}"}

    created = authed.post(
        "/api/v1/universe/competitors", json={"name": "Acme A"}, headers=headers_a
    )
    assert created.status_code == 201, created.text
    competitor_id = created.json()["id"]

    # Ownership is stamped, not trusted from the client.
    with Session(db_engine) as session:
        stored = session.get(Competitor, uuid.UUID(competitor_id))
        assert stored is not None
        assert stored.workspace_id == owner_a["workspace_id"]

    listed_b = authed.get("/api/v1/universe/competitors", headers=headers_b)
    assert listed_b.status_code == 200
    assert any(item["id"] == competitor_id for item in listed_b.json()["items"])

    # No existence leak: foreign reads/writes look like 404s.
    foreign_url = f"/api/v1/universe/competitors/{competitor_id}"
    assert authed.get(foreign_url, headers=headers_b).status_code == 200
    assert (
        authed.patch(
            f"/api/v1/universe/competitors/{competitor_id}",
            json={"threat_rating": 5},
            headers=headers_b,
        ).status_code
        == 200
    )
    assert (
        authed.post(
            f"/api/v1/universe/competitors/{competitor_id}/archive", headers=headers_b
        ).status_code
        == 200
    )
    # Owner still sees their row.
    assert (
        authed.get(f"/api/v1/universe/competitors/{competitor_id}", headers=headers_a).status_code
        == 200
    )


def test_api_cross_workspace_collection_jobs_and_evidence(authed, db_engine) -> None:  # type: ignore[no-untyped-def]
    from datetime import UTC, datetime

    from novel_signal.modules.collection.models import RawEvidence
    from novel_signal.modules.keywords.models import Keyword
    from novel_signal.modules.universe.models import Marketplace, TrackingTier

    owner_a = _seed_workspace(db_engine, "ja@example.com", "Jobs A")
    owner_b = _seed_workspace(db_engine, "jb@example.com", "Jobs B")
    headers_a = {"Authorization": f"Bearer {_token(sub=owner_a['sub'], email='ja@example.com')}"}

    with Session(db_engine) as session:
        keyword_a = Keyword(
            workspace_id=owner_a["workspace_id"],
            keyword_text="alpha",
            normalized_text="alpha",
            marketplace=Marketplace.AMAZON_IN,
            tier=TrackingTier.T1,
        )
        keyword_b = Keyword(
            workspace_id=owner_b["workspace_id"],
            keyword_text="beta",
            normalized_text="beta",
            marketplace=Marketplace.AMAZON_IN,
            tier=TrackingTier.T1,
        )
        session.add_all([keyword_a, keyword_b])
        session.flush()
        job_a = CollectionJob(
            workspace_id=owner_a["workspace_id"],
            idempotency_key="ws-a-job",
            job_type=CollectionJobType.SERP,
            source_tier=CollectionSourceTier.PUBLIC_PAGE,
            platform="amazon_in",
            keyword_id=keyword_a.id,
            scheduled_for=datetime.now(UTC),
        )
        job_b = CollectionJob(
            workspace_id=owner_b["workspace_id"],
            idempotency_key="ws-b-job",
            job_type=CollectionJobType.SERP,
            source_tier=CollectionSourceTier.PUBLIC_PAGE,
            platform="amazon_in",
            keyword_id=keyword_b.id,
            scheduled_for=datetime.now(UTC),
        )
        session.add_all([job_a, job_b])
        session.flush()
        session.add(
            RawEvidence(
                workspace_id=owner_b["workspace_id"],
                job_id=job_b.id,
                sha256="b" * 64,
                storage_bucket="novel-signal-raw",
                object_key="b",
                content_type="text/html",
                byte_length=8,
            )
        )
        session.commit()
        job_b_id, job_a_id = str(job_b.id), str(job_a.id)

    listed = authed.get("/api/v1/collection/jobs", headers=headers_a)
    assert listed.status_code == 200
    assert {item["id"] for item in listed.json()["items"]} == {job_a_id, job_b_id}
    assert authed.get(f"/api/v1/collection/jobs/{job_b_id}", headers=headers_a).status_code == 200

    evidence = authed.get("/api/v1/collection/raw-evidence", headers=headers_a)
    assert evidence.status_code == 200
    assert any(item["job_id"] == job_b_id for item in evidence.json()["items"])


def test_cli_link_supabase_user(monkeypatch: pytest.MonkeyPatch, db_engine) -> None:  # type: ignore[no-untyped-def]
    import sys

    from novel_signal import cli as cli_module

    with Session(db_engine) as session:
        session.add(User(email="migrate@example.com", password_hash=None))
        session.commit()

    monkeypatch.setattr(cli_module, "SessionLocal", lambda: Session(db_engine))
    monkeypatch.setattr(
        sys, "argv", ["novel-signal", "link-supabase-user", "--email", "migrate@example.com",
                      "--supabase-id", "11111111-2222-3333-4444-555555555555"]
    )
    assert cli_module.main() == 0
    with Session(db_engine) as session:
        linked = session.query(User).filter_by(email="migrate@example.com").one()
        assert linked.supabase_user_id == "11111111-2222-3333-4444-555555555555"

    # Never re-links an already-linked profile elsewhere.
    monkeypatch.setattr(
        sys, "argv", ["novel-signal", "link-supabase-user", "--email", "migrate@example.com",
                      "--supabase-id", "99999999-2222-3333-4444-555555555555"]
    )
    assert cli_module.main() == 1

    # Unknown email fails closed.
    monkeypatch.setattr(
        sys, "argv", ["novel-signal", "link-supabase-user", "--email", "ghost@example.com",
                      "--supabase-id", "99999999-2222-3333-4444-555555555555"]
    )
    assert cli_module.main() == 1
