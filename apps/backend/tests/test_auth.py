import novel_signal.main as main_module
from fastapi.testclient import TestClient
from novel_signal.config import Settings, get_settings
from novel_signal.main import app


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
