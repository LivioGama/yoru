"""API-key endpoints + X-API-Key auth vector.

Ported from community PR TsukumoHQ/yoru#6 (Livio Gamassia), hardened:
  - raw key shown once, sha256-only at rest
  - `expires_at` settable at creation and enforced at resolution
  - API-key callers refused on credential-minting endpoints (containment:
    a leaked key can't mint hook-tokens or more API keys)
  - `last_used_at` refresh throttled to one write per 60s

Mirrors the hook-token test contract (AUTH-V0 §1(a)) for revoke semantics.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from apps.api.api.dependencies.auth import SESSION_COOKIE_NAME

_PREFIX = "yoru_ak_"


def _create_key(
    client: TestClient,
    cookie: str,
    label: str | None = None,
    expires_at: str | None = None,
    scopes: list[str] | None = None,
) -> dict:
    """Create an API key as the cookie's identity; returns the response json."""
    client.cookies.set(SESSION_COOKIE_NAME, cookie)
    payload: dict = {}
    if label is not None:
        payload["label"] = label
    if expires_at is not None:
        payload["expires_at"] = expires_at
    if scopes is not None:
        payload["scopes"] = scopes
    resp = client.post("/api/v1/auth/api-keys", json=payload)
    assert resp.status_code == 201, resp.text
    client.cookies.delete(SESSION_COOKIE_NAME)
    return resp.json()


# 1. Create happy path — raw key returned once, prefix persisted,
#    least-privilege default scope
def test_create_happy_path(client: TestClient, session_cookie_for) -> None:
    body = _create_key(client, session_cookie_for("alice@example.com"), "ci-runner")
    assert body["key"].startswith(_PREFIX)
    assert body["key_prefix"] == body["key"][len(_PREFIX):len(_PREFIX) + 8]
    assert body["label"] == "ci-runner"
    assert body["scopes"] == ["ingest"]
    assert body["expires_at"] is None


# 2. Create requires auth; scopes validated
def test_create_requires_auth(client: TestClient) -> None:
    resp = client.post("/api/v1/auth/api-keys", json={})
    assert resp.status_code == 401


def test_create_rejects_bad_scopes(client: TestClient, session_cookie_for) -> None:
    client.cookies.set(SESSION_COOKIE_NAME, session_cookie_for("alice@example.com"))
    assert (
        client.post(
            "/api/v1/auth/api-keys", json={"scopes": ["admin"]}
        ).status_code
        == 400
    )
    assert (
        client.post("/api/v1/auth/api-keys", json={"scopes": []}).status_code
        == 400
    )


# 3. X-API-Key authenticates ingest (the headless/CI use case)
def test_api_key_authenticates_ingest(client: TestClient, session_cookie_for) -> None:
    body = _create_key(
        client,
        session_cookie_for("alice@example.com"),
        scopes=["ingest", "read"],
    )
    resp = client.post(
        "/api/v1/sessions/events",
        headers={"X-API-Key": body["key"]},
        json={
            "events": [
                {
                    "session_id": "sess-apikey-01",
                    "kind": "tool_use",
                    "tool": "Bash",
                    "content": "echo hi",
                }
            ]
        },
    )
    assert resp.status_code == 202, resp.text
    # Events bind to the key's user, not an unauthenticated fallback.
    detail = client.get(
        "/api/v1/sessions/sess-apikey-01",
        headers={"X-API-Key": body["key"]},
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["user"] == "alice@example.com"


# 4. Malformed / unknown / revoked keys → 401
def test_bad_keys_rejected(client: TestClient, session_cookie_for) -> None:
    assert (
        client.get(
            "/api/v1/auth/hook-tokens", headers={"X-API-Key": "not-a-key"}
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/api/v1/auth/hook-tokens",
            headers={"X-API-Key": _PREFIX + "A" * 43},
        ).status_code
        == 401
    )

    cookie = session_cookie_for("alice@example.com")
    body = _create_key(client, cookie)
    client.cookies.set(SESSION_COOKIE_NAME, cookie)
    assert client.delete(f"/api/v1/auth/api-key/{body['id']}").status_code == 204
    client.cookies.delete(SESSION_COOKIE_NAME)
    resp = client.get(
        "/api/v1/auth/hook-tokens", headers={"X-API-Key": body["key"]}
    )
    assert resp.status_code == 401


# 5. expires_at — past at creation → 400; expired at use → 401
def test_expiry(client: TestClient, session_cookie_for, db_session) -> None:
    cookie = session_cookie_for("alice@example.com")
    client.cookies.set(SESSION_COOKIE_NAME, cookie)
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    resp = client.post("/api/v1/auth/api-keys", json={"expires_at": past})
    assert resp.status_code == 400
    client.cookies.delete(SESSION_COOKIE_NAME)

    future = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    body = _create_key(client, cookie, expires_at=future)
    assert body["expires_at"] is not None

    # Flip the row to expired and verify the vector dies.
    from apps.api.api.routers.receipt.models import ApiKey

    row = db_session.get(ApiKey, body["id"])
    row.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(
        seconds=1
    )
    db_session.add(row)
    db_session.commit()
    resp = client.get(
        "/api/v1/auth/hook-tokens", headers={"X-API-Key": body["key"]}
    )
    assert resp.status_code == 401


# 6. Containment — an API key cannot mint credentials
def test_api_key_cannot_mint_credentials(
    client: TestClient, session_cookie_for
) -> None:
    body = _create_key(client, session_cookie_for("alice@example.com"))
    headers = {"X-API-Key": body["key"]}

    # Can't mint hook-tokens…
    resp = client.post(
        "/api/v1/auth/hook-token", headers=headers, json={"user": "x@y"}
    )
    assert resp.status_code == 403, resp.text
    # …can't mint more API keys…
    resp = client.post("/api/v1/auth/api-keys", headers=headers, json={})
    assert resp.status_code == 403, resp.text
    # …can't list, revoke, or rotate them either.
    assert client.get("/api/v1/auth/api-keys", headers=headers).status_code == 403
    assert (
        client.delete(
            f"/api/v1/auth/api-key/{body['id']}", headers=headers
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/auth/api-key/{body['id']}/rotate", headers=headers
        ).status_code
        == 403
    )


def test_read_scoped_key_still_denied_on_key_management(
    client: TestClient, session_cookie_for
) -> None:
    # GET /auth/api-keys passes the scope layer ('read' covers GET) — the
    # deny_api_key_auth guard must still refuse it (defense-in-depth).
    body = _create_key(
        client, session_cookie_for("alice@example.com"), scopes=["read"]
    )
    resp = client.get("/api/v1/auth/api-keys", headers={"X-API-Key": body["key"]})
    assert resp.status_code == 403, resp.text


# 6b. Scope enforcement — least privilege actually enforced
def test_scope_enforcement(client: TestClient, session_cookie_for) -> None:
    cookie = session_cookie_for("alice@example.com")
    ingest_only = _create_key(client, cookie)  # default ['ingest']
    read_only = _create_key(client, cookie, scopes=["read"])

    # ingest-only key cannot read…
    resp = client.get(
        "/api/v1/sessions/whatever", headers={"X-API-Key": ingest_only["key"]}
    )
    assert resp.status_code == 403, resp.text
    # …read-only key cannot ingest.
    resp = client.post(
        "/api/v1/sessions/events",
        headers={"X-API-Key": read_only["key"]},
        json={"events": [{"session_id": "s-scope", "kind": "tool_use", "tool": "Bash"}]},
    )
    assert resp.status_code == 403, resp.text


# 7. List scoped to caller; raw key never in list output
def test_list_scoped_and_no_raw_key(client: TestClient, session_cookie_for) -> None:
    alice = session_cookie_for("alice@example.com")
    bob = session_cookie_for("bob@example.com")
    a_key = _create_key(client, alice, "laptop")
    _create_key(client, bob, "other")

    client.cookies.set(SESSION_COOKIE_NAME, alice)
    resp = client.get("/api/v1/auth/api-keys")
    assert resp.status_code == 200
    items = resp.json()
    assert [i["id"] for i in items] == [a_key["id"]]
    assert "key" not in items[0]
    assert items[0]["key_prefix"] == a_key["key_prefix"]


# 8. Revoke semantics — 404 unknown AND foreign (no existence oracle,
#    deliberate divergence from the hook-token 401 contract), idempotent 204
def test_revoke_semantics(client: TestClient, session_cookie_for) -> None:
    alice = session_cookie_for("alice@example.com")
    bob = session_cookie_for("bob@example.com")
    key = _create_key(client, alice)

    client.cookies.set(SESSION_COOKIE_NAME, alice)
    assert client.delete("/api/v1/auth/api-key/nope").status_code == 404
    client.cookies.set(SESSION_COOKIE_NAME, bob)
    assert client.delete(f"/api/v1/auth/api-key/{key['id']}").status_code == 404
    client.cookies.set(SESSION_COOKIE_NAME, alice)
    assert client.delete(f"/api/v1/auth/api-key/{key['id']}").status_code == 204
    assert client.delete(f"/api/v1/auth/api-key/{key['id']}").status_code == 204


# 9. last_used_at set on first successful use (freshness indicator)
def test_last_used_at_updates(client: TestClient, session_cookie_for) -> None:
    cookie = session_cookie_for("alice@example.com")
    body = _create_key(client, cookie)

    client.cookies.set(SESSION_COOKIE_NAME, cookie)
    before = client.get("/api/v1/auth/api-keys").json()[0]["last_used_at"]
    client.cookies.delete(SESSION_COOKIE_NAME)
    assert before is None

    ingest = client.post(
        "/api/v1/sessions/events",
        headers={"X-API-Key": body["key"]},
        json={"events": [{"session_id": "s-lu", "kind": "tool_use", "tool": "Bash"}]},
    )
    assert ingest.status_code == 202, ingest.text

    client.cookies.set(SESSION_COOKIE_NAME, cookie)
    after = client.get("/api/v1/auth/api-keys").json()[0]["last_used_at"]
    assert after is not None


# 10. Rotation — replacement carries label/scopes/expiry, old key dies,
#     no existence oracle, 409 on already-revoked
def test_rotate_happy_path(client: TestClient, session_cookie_for) -> None:
    cookie = session_cookie_for("alice@example.com")
    old = _create_key(client, cookie, "ci-runner", scopes=["ingest", "read"])

    client.cookies.set(SESSION_COOKIE_NAME, cookie)
    resp = client.post(f"/api/v1/auth/api-key/{old['id']}/rotate")
    assert resp.status_code == 201, resp.text
    new = resp.json()
    client.cookies.delete(SESSION_COOKIE_NAME)

    assert new["key"] != old["key"]
    assert new["id"] != old["id"]
    assert new["label"] == "ci-runner"
    assert new["scopes"] == ["ingest", "read"]

    # New key works; old key is revoked.
    assert (
        client.get(
            "/api/v1/sessions/s-nope", headers={"X-API-Key": new["key"]}
        ).status_code
        == 404  # authenticated, session simply doesn't exist
    )
    assert (
        client.get(
            "/api/v1/sessions/s-nope", headers={"X-API-Key": old["key"]}
        ).status_code
        == 401
    )


def test_rotate_edge_cases(client: TestClient, session_cookie_for) -> None:
    alice = session_cookie_for("alice@example.com")
    bob = session_cookie_for("bob@example.com")
    key = _create_key(client, alice)

    # Unknown / foreign → 404 (same no-oracle rule as revoke).
    client.cookies.set(SESSION_COOKIE_NAME, alice)
    assert client.post("/api/v1/auth/api-key/nope/rotate").status_code == 404
    client.cookies.set(SESSION_COOKIE_NAME, bob)
    assert (
        client.post(f"/api/v1/auth/api-key/{key['id']}/rotate").status_code == 404
    )

    # Already revoked → 409.
    client.cookies.set(SESSION_COOKIE_NAME, alice)
    assert client.delete(f"/api/v1/auth/api-key/{key['id']}").status_code == 204
    assert (
        client.post(f"/api/v1/auth/api-key/{key['id']}/rotate").status_code == 409
    )
