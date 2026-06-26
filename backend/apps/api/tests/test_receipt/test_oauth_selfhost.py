"""GitHub OAuth + signout degrade gracefully on a self-host (local) deploy.

TSU-63 fixes #3/#4. GitHub OAuth is a Supabase-only feature: `github_start`
instantiated a `SupabaseManager()` OUTSIDE its try/except, so on a local
instance (no SUPABASE_* env) it 500'd instead of falling back to password
sign-in. Signout instantiated one too (inside a try, so it degraded, but
needlessly). Both are now gated on AUTH_PROVIDER.

These tests mount the real CookieAuthRouter and rely on the default
AUTH_PROVIDER=local (the test env sets no SUPABASE_*).
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.api.dependencies.auth import SESSION_COOKIE_NAME
from apps.api.api.routers.auth.cookie_router import (
    REFRESH_COOKIE_NAME,
    CookieAuthRouter,
)


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(CookieAuthRouter().get_router(), prefix="/api/v1")
    # follow_redirects=False so we can assert the 302 target instead of chasing
    # it to an unmounted /signin page.
    return TestClient(app, follow_redirects=False)


def test_github_start_degrades_to_signin_on_self_host() -> None:
    r = _client().get("/api/v1/auth/github/start")
    # Must be a clean redirect, NOT a 500 from a SupabaseManager() on missing env.
    assert r.status_code == 302
    assert "oauth-unavailable" in r.headers["location"]


def test_github_callback_degrades_on_self_host() -> None:
    r = _client().get("/api/v1/auth/github/callback?code=whatever")
    assert r.status_code == 302
    assert "oauth-unavailable" in r.headers["location"]


def test_signout_succeeds_without_supabase_on_self_host() -> None:
    client = _client()
    client.cookies.set(SESSION_COOKIE_NAME, "dummy-access")
    client.cookies.set(REFRESH_COOKIE_NAME, "dummy-refresh")
    # Even WITH both cookies present (the branch that used to hit Supabase),
    # local must clear cookies and return 204 — no SupabaseManager(), no error.
    r = client.post("/api/v1/auth/session/signout")
    assert r.status_code == 204
