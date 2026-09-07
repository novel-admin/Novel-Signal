"""Opt-in live Supabase integration test (real credentials only).

Run only when real Supabase credentials are available:

    $env:SUPABASE_URL="https://xyzcompany.supabase.co"
    $env:SUPABASE_ANON_KEY="<anon>"
    $env:SUPABASE_TEST_EMAIL="<owner-created user>"
    $env:SUPABASE_TEST_PASSWORD="<password>"
    .\\.venv\\Scripts\\python.exe -m pytest apps/backend/tests/test_supabase_live.py -q

Skipped automatically in normal CI (mocked JWTs are used instead).
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    not (
        os.environ.get("SUPABASE_URL")
        and os.environ.get("SUPABASE_ANON_KEY")
        and os.environ.get("SUPABASE_TEST_EMAIL")
        and os.environ.get("SUPABASE_TEST_PASSWORD")
    ),
    reason="Live Supabase credentials not configured (opt-in only).",
)


def test_live_login_flow() -> None:
    """Internal tool: admin-created email+password signs in, no MFA involved."""
    try:
        from supabase import create_client  # type: ignore[import-not-found]
    except ImportError:
        pytest.skip("supabase-py not installed for live test.")
        return
    url = os.environ["SUPABASE_URL"]
    anon = os.environ["SUPABASE_ANON_KEY"]
    client = create_client(url, anon)
    credentials = {
        "email": os.environ["SUPABASE_TEST_EMAIL"],
        "password": os.environ["SUPABASE_TEST_PASSWORD"],
    }
    response = client.auth.sign_in_with_password(credentials)
    assert response.session is not None
    assert response.user is not None
    # Manual steps after this: call /api/v1/auth/me with the access token,
    # verify workspace membership, roles, and cross-workspace isolation.
