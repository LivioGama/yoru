"""Service-token endpoints on a self-hosted (AUTH_PROVIDER=local) deploy.

TSU-63 fix #2. The create/list/revoke endpoints authorized admins via the
Supabase client (`_require_org_admin` → `auth.get_user`) and resolved the
workspace via Supabase PostgREST (`_org_default_workspace_id`) — both 401/500
on a local store, so the whole service-token subsystem was unusable on
self-host.

Self-host is single-tenant: any authenticated dashboard user manages service
tokens (README: "the first registered user becomes the admin"). These tests
exercise that local path end to end. The cloud (AUTH_PROVIDER=supabase) path is
untouched and not exercised here.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from apps.api.api.dependencies.auth import SESSION_COOKIE_NAME

_ORG = "acme"


def _login(client: TestClient, session_cookie_for, email: str = "admin@yoru.test") -> None:
    client.cookies.set(SESSION_COOKIE_NAME, session_cookie_for(email))


def test_create_list_revoke_self_host(client: TestClient, session_cookie_for) -> None:
    _login(client, session_cookie_for)

    # create — authorized by the dashboard session cookie alone (no Supabase).
    r = client.post(
        "/api/v1/auth/service-token",
        json={"org_id": _ORG, "label": "ci-runner", "scopes": ["events:write"]},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["token"].startswith("rcpt_s_")
    assert body["org_id"] == _ORG
    token_id = body["id"]

    # list — same org, must include the token we just minted.
    r = client.get(f"/api/v1/auth/service-tokens?org_id={_ORG}")
    assert r.status_code == 200, r.text
    listed = r.json()
    assert any(t["id"] == token_id for t in listed)
    assert all(t["org_id"] == _ORG for t in listed)
    # token_hash must never leak through the list item.
    assert all("token_hash" not in t for t in listed)

    # revoke — 204, idempotent-safe.
    r = client.delete(f"/api/v1/auth/service-token/{token_id}")
    assert r.status_code == 204, r.text

    # after revoke the row carries revoked_at (still listed, but revoked).
    r = client.get(f"/api/v1/auth/service-tokens?org_id={_ORG}")
    revoked = next(t for t in r.json() if t["id"] == token_id)
    assert revoked["revoked_at"] is not None


def test_create_requires_dashboard_session(client: TestClient) -> None:
    # No session cookie → 401 (you manage tokens from the signed-in dashboard).
    r = client.post(
        "/api/v1/auth/service-token",
        json={"org_id": _ORG, "label": "x"},
    )
    assert r.status_code == 401


def test_list_scoped_to_org(client: TestClient, session_cookie_for) -> None:
    _login(client, session_cookie_for)
    client.post(
        "/api/v1/auth/service-token",
        json={"org_id": "org-a", "label": "a"},
    )
    client.post(
        "/api/v1/auth/service-token",
        json={"org_id": "org-b", "label": "b"},
    )
    r = client.get("/api/v1/auth/service-tokens?org_id=org-a")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["org_id"] == "org-a"
