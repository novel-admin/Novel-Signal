from fastapi.testclient import TestClient
from novel_signal.config import Settings
from novel_signal.main import create_app

VERCEL_ORIGIN = "https://novel-signal-web.vercel.app"


def test_api_response_includes_cors_headers_for_vercel_origin() -> None:
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            allowed_origins=f"http://localhost:3000,http://localhost:5173,{VERCEL_ORIGIN}",
        )
    )

    response = TestClient(app).get("/api/v1/sources", headers={"Origin": VERCEL_ORIGIN})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == VERCEL_ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"


def test_options_preflight_reaches_cors_before_auth_middleware() -> None:
    app = create_app(
        Settings(
            _env_file=None,
            app_env="test",
            allowed_origins=VERCEL_ORIGIN,
        )
    )
    client = TestClient(app)

    for path in (
        "/api/v1/sources",
        "/api/v1/universe/products",
        "/api/v1/collection/jobs",
        "/api/v1/rank-visibility/captures",
    ):
        response = client.options(
            path,
            headers={
                "Origin": VERCEL_ORIGIN,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )

        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == VERCEL_ORIGIN
        assert "GET" in response.headers["access-control-allow-methods"]
        assert "authorization" in response.headers["access-control-allow-headers"]
