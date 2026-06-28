"""Wave-13 B1 — slowapi-based rate limiting for Receipt v0.

Three rules are applied via `@limiter.limit(...)` decorators on the
endpoints themselves (see `auth_router.py`, `events_router.py`):

| Route                           | Limit     | Key                      |
| ------------------------------- | --------- | ------------------------ |
| POST /api/v1/auth/hook-token    | 10/minute | remote IP                |
| POST /api/v1/sessions/events    | 300/minute| hook-token hash (or IP)  |

Enablement (`_env_enabled`): explicit `RATELIMIT_ENABLED` wins (on/off); when
unset it defaults **on in production** (`ENV=production`) and **off** in dev /
pytest / smoke. This means a real self-host deploy is abuse-guarded on the
public viral surface out of the box (pre-viral hardening, TSU-154) without the
operator remembering a flag, while the suite + `smoke-us14.sh` wedge stay
unimpeded. Tests that exercise the limiter still flip the env + `limiter.enabled
= True` explicitly.

The single `/api/v1/ingest` alias called out in BACKEND-API-V0.md is not
yet mounted — TODO when/if that alias lands: apply the same 300/min rule.
"""
from __future__ import annotations

import hashlib
import os

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def _env_enabled() -> bool:
    v = os.environ.get("RATELIMIT_ENABLED", "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    # Unset → on in production (pre-viral hardening: the public share surface
    # must be guarded by default), off in dev/pytest so the suite is deterministic.
    return os.environ.get("ENV", "").strip().lower() == "production"


def hook_token_key(request: Request) -> str:
    """Bucket ingest by hook-token hash; fall back to IP.

    Rationale: one abusive client sharing a pool of IPs (NAT, CI runners)
    would otherwise evade a pure-IP limiter. Bucketing on the token hash
    keeps a leaked-token abuser pinned. We hash so buckets never store
    raw credentials.
    """
    auth = request.headers.get("authorization", "") or ""
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
        if token:
            return "tok:" + hashlib.sha256(token.encode()).hexdigest()[:16]
    return "ip:" + (get_remote_address(request) or "unknown")


limiter = Limiter(
    key_func=get_remote_address,
    enabled=_env_enabled(),
    headers_enabled=True,
    default_limits=[],
)


__all__ = ["limiter", "hook_token_key", "get_remote_address"]
