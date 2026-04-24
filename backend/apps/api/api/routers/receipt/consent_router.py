"""Share-consent endpoint — #79 follow-up.

Tracks the one-time "I understand what public means" acknowledgment at
the user-row level so the decision travels with the account instead of
being tied to a specific browser's localStorage or a specific machine's
~/.config file.

  GET  /api/v1/account/share-consent   → {consented, at}
  POST /api/v1/account/share-consent   → {consented: true, at: <now>}
                                          (idempotent — stamps once,
                                          subsequent calls return the
                                          original timestamp)

Both endpoints require auth via `require_current_user` (bearer token or
cookie session — both the CLI and the dashboard can call them). There is
intentionally no "revoke consent" path: the user can unpublish a specific
session at any time via /share/revoke, but the *understanding* that
"public" means public is a one-way door once acknowledged.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlmodel import Session as SQLSession

from .db import get_session
from .deps import require_current_user
from .models import ShareConsentOut, User


class ShareConsentRouter:
    """Per-user share-disclosure consent tracking."""

    def __init__(self) -> None:
        self.router = APIRouter(prefix="/account", tags=["receipt:consent"])
        self._setup_routes()

    def get_router(self) -> APIRouter:
        return self.router

    def _setup_routes(self) -> None:
        self.router.get(
            "/share-consent", response_model=ShareConsentOut
        )(self.get_share_consent)
        self.router.post(
            "/share-consent", response_model=ShareConsentOut
        )(self.post_share_consent)

    def get_share_consent(
        self,
        db: SQLSession = Depends(get_session),
        current_user: str = Depends(require_current_user),
    ) -> ShareConsentOut:
        row = db.get(User, current_user)
        if row is None or row.share_consent_given_at is None:
            return ShareConsentOut(consented=False, at=None)
        return ShareConsentOut(
            consented=True, at=row.share_consent_given_at
        )

    def post_share_consent(
        self,
        db: SQLSession = Depends(get_session),
        current_user: str = Depends(require_current_user),
    ) -> ShareConsentOut:
        """Idempotent. First call stamps share_consent_given_at = now();
        subsequent calls return the original stamp without overwriting —
        we care about the *earliest* acknowledgment for any future audit
        surface, not the most recent."""
        row = db.get(User, current_user)
        if row is None:
            # Lazy-upsert — the users row is normally created by the welcome-
            # email trigger, but a CLI-only user who shares before they've
            # ever hit the dashboard might not have a row yet.
            row = User(email=current_user)
            db.add(row)
        if row.share_consent_given_at is None:
            row.share_consent_given_at = datetime.now(timezone.utc)
            db.add(row)
            db.commit()
            db.refresh(row)
        return ShareConsentOut(
            consented=True, at=row.share_consent_given_at
        )
