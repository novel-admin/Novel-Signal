"""Legacy dashboard access-code auth is removed from the production path.

Supabase Auth is the only identity provider. See test_supabase_auth.py for
the production behavior.
"""

from fastapi.testclient import TestClient
from novel_signal.main import app


def test_health_endpoints_remain_public() -> None:
    client = TestClient(app)
    assert client.get("/api/v1/health/live").status_code == 200
    assert client.get("/api/v1/health/ready").status_code == 200


def test_legacy_dashboard_login_is_gone() -> None:
    client = TestClient(app)
    assert client.post("/api/v1/auth/login", json={"code": "demo-code"}).status_code == 404
    assert client.get("/api/v1/auth/session").status_code == 404
