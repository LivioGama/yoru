"""Integration tests — hook-token endpoints (§4.6–§4.8).

Six atomic cases per CTO brief; end-to-end via TestClient, no router edits.
Contract: vault/BACKEND-API-V0.md §4.6–§4.8, vault/AUTH-V0.md §1(a).
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from apps.api.api.dependencies.auth import SESSION_COOKIE_NAME


def _mint(client: TestClient, cookie: str, label: str | None = None) -> dict:
    """Mint a hook-token as the cookie's identity (v1: body.user is ignored;
    the caller is taken from the `rcpt_session` cookie). Returns the response
    json — `token` is the raw bearer, `user_id` is the row id."""
    client.cookies.set(SESSION_COOKIE_NAME, cookie)
    # `user` is a required-but-ignored body field (v1 hardening): identity comes
    # from the cookie. Send a decoy value to prove it never rebinds the token.
    payload: dict = {"user": "ignored@body"}
    if label is not None:
        payload["label"] = label
    resp = client.post("/api/v1/auth/hook-token", json=payload)
    assert resp.status_code == 201, resp.text
    client.cookies.delete(SESSION_COOKIE_NAME)
    return resp.json()


# 1. Mint happy path — §4.6
def test_mint_happy_path(client: TestClient, session_cookie_for) -> None:
    client.cookies.set(SESSION_COOKIE_NAME, session_cookie_for("alice@example.com"))
    resp = client.post(
        "/api/v1/auth/hook-token",
        json={"user": "ignored@body", "label": "laptop"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["token"].startswith("rcpt_")
    # Bound to the cookie identity, not the decoy body.user.
    assert body["user"] == "alice@example.com"


# 2. List requires auth — §4.7
def test_list_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/v1/auth/hook-tokens")
    assert resp.status_code == 401


# 3. List scoped to caller — §4.7 (cross-user isolation)
def test_list_scoped_to_caller(client: TestClient, session_cookie_for) -> None:
    alice = session_cookie_for("alice@example.com")
    bob = session_cookie_for("bob@example.com")
    a1 = _mint(client, alice, "laptop")
    _mint(client, alice, "desktop")
    bob_tok = _mint(client, bob, "laptop")

    resp = client.get(
        "/api/v1/auth/hook-tokens",
        headers={"Authorization": f"Bearer {a1['token']}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    ids = {row["id"] for row in body}
    assert bob_tok["user_id"] not in ids


# 4. Revoke happy (idempotent) — §4.8
def test_revoke_happy_is_idempotent(client: TestClient, session_cookie_for) -> None:
    alice = session_cookie_for("alice@example.com")
    auth = _mint(client, alice, "auth")  # bearer, kept live
    target = _mint(client, alice, "to-revoke")
    headers = {"Authorization": f"Bearer {auth['token']}"}

    r1 = client.delete(f"/api/v1/auth/hook-token/{target['user_id']}", headers=headers)
    assert r1.status_code == 204, r1.text

    r2 = client.delete(f"/api/v1/auth/hook-token/{target['user_id']}", headers=headers)
    assert r2.status_code == 204, r2.text


# 5. Revoke cross-user → 401 — §4.8 acceptance + AUTH-V0 §1(a)
def test_revoke_cross_user_returns_401(client: TestClient, session_cookie_for) -> None:
    alice = _mint(client, session_cookie_for("alice@example.com"), "laptop")
    bob = _mint(client, session_cookie_for("bob@example.com"), "laptop")

    resp = client.delete(
        f"/api/v1/auth/hook-token/{bob['user_id']}",
        headers={"Authorization": f"Bearer {alice['token']}"},
    )
    assert resp.status_code == 401


# 6. Revoke unknown id → 404 — §4.8
def test_revoke_unknown_returns_404(client: TestClient, session_cookie_for) -> None:
    alice = _mint(client, session_cookie_for("alice@example.com"), "laptop")
    resp = client.delete(
        "/api/v1/auth/hook-token/00000000000000000000000000000000",
        headers={"Authorization": f"Bearer {alice['token']}"},
    )
    assert resp.status_code == 404
