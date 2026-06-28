"""TSU-154 — public-surface abuse-guard unit tests.

Complements test_rate_limit.py (ingest token-bucket → 429) and
test_body_size_cap.py (oversized POST → 413). Covers the two guards those
don't:
  - the per-batch event cap (EventsBatchIn max_length=1000), and
  - the rate-limit enablement default (auto-on in production, off in
    dev/pytest) added for pre-viral hardening.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.api.api.core.ratelimit import _env_enabled
from apps.api.api.routers.receipt.models import EventsBatchIn


def _events(n: int) -> list[dict]:
    # session_id is the only required EventIn field.
    return [{"session_id": "s1"} for _ in range(n)]


# ── per-batch event cap (EventsBatchIn.events max_length=1000) ──────────────
def test_batch_cap_accepts_up_to_1000() -> None:
    batch = EventsBatchIn(events=_events(1000))
    assert len(batch.events) == 1000


def test_batch_cap_rejects_over_1000() -> None:
    with pytest.raises(ValidationError):
        EventsBatchIn(events=_events(1001))


def test_batch_rejects_empty() -> None:
    with pytest.raises(ValidationError):
        EventsBatchIn(events=[])


# ── rate-limit enablement default (TSU-154) ────────────────────────────────
def test_ratelimit_disabled_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("RATELIMIT_ENABLED", raising=False)
    monkeypatch.delenv("ENV", raising=False)
    assert _env_enabled() is False


def test_ratelimit_auto_on_in_production(monkeypatch) -> None:
    monkeypatch.delenv("RATELIMIT_ENABLED", raising=False)
    monkeypatch.setenv("ENV", "production")
    assert _env_enabled() is True


def test_ratelimit_explicit_off_overrides_production(monkeypatch) -> None:
    monkeypatch.setenv("RATELIMIT_ENABLED", "0")
    monkeypatch.setenv("ENV", "production")
    assert _env_enabled() is False


def test_ratelimit_explicit_on_without_production(monkeypatch) -> None:
    monkeypatch.setenv("RATELIMIT_ENABLED", "1")
    monkeypatch.delenv("ENV", raising=False)
    assert _env_enabled() is True
