"""Mock BillingAdapter — records every call + returns stub URLs.

Used in dev + tests + CI. Never touches the network.
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

from app.adapters.billing.base import BillingAdapter

logger = logging.getLogger(__name__)


class MockBillingAdapter(BillingAdapter):
    """Thread-safe in-memory mock."""

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._events: dict[str, dict[str, Any]] = {}  # stripe_event_id → event
        self._subscriptions: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        # Dev secret for signing/verification (mock accepts unsigned
        # payloads — the secret is recorded for parity with real).
        self._webhook_secret = "mock-webhook-secret-change-me"

    # ── Checkout ──────────────────────────────────────────────────
    def create_checkout_session(
        self,
        *,
        team_id: str,
        plan: str,
        success_url: str,
        cancel_url: str,
    ) -> dict[str, str]:
        session_id = f"mock_cs_{uuid.uuid4().hex[:16]}"
        with self._lock:
            self._sessions[session_id] = {
                "team_id": team_id,
                "plan": plan,
                "success_url": success_url,
                "cancel_url": cancel_url,
                "created_at": _now_iso(),
            }
        url = f"https://billing-mock.example.com/checkout/{session_id}"
        logger.info(
            "[mock-billing] checkout session %s team=%s plan=%s",
            session_id,
            team_id,
            plan,
        )
        return {"url": url, "session_id": session_id}

    # ── Portal ────────────────────────────────────────────────────
    def create_portal_session(self, *, team_id: str, return_url: str) -> dict[str, str]:
        session_id = f"mock_ps_{uuid.uuid4().hex[:16]}"
        with self._lock:
            self._sessions[session_id] = {
                "team_id": team_id,
                "kind": "portal",
                "return_url": return_url,
                "created_at": _now_iso(),
            }
        url = f"https://billing-mock.example.com/portal/{session_id}"
        return {"url": url, "session_id": session_id}

    # ── Subscription ─────────────────────────────────────────────
    def get_subscription(self, *, subscription_id: str) -> Any:  # type: ignore[no-any-return, unused-ignore]
        with self._lock:
            sub_raw: Any = self._subscriptions.get(subscription_id)
            return sub_raw

    # ── Webhook ──────────────────────────────────────────────────
    def verify_webhook_signature(self, *, payload: bytes, signature_header: str) -> dict[str, Any]:
        """In mock mode, accept any JSON payload (skip signature).

        Real mode (T-405) would verify HMAC-SHA256 against the webhook
        secret. For tests, we just parse + dedupe by event id.
        """
        import json

        try:
            event = json.loads(payload)
        except (ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid JSON payload: {exc}") from exc

        event_id = event.get("id")
        if not event_id:
            raise ValueError("event missing 'id' field")

        # Idempotency: replay → return cached event without re-processing
        with self._lock:
            cached = self._events.get(event_id)
            if cached is not None:
                return cached
            self._events[event_id] = event
        return event

    # ── Test helpers ─────────────────────────────────────────────
    def seed_subscription(
        self, *, subscription_id: str, team_id: str, plan: str = "starter"
    ) -> None:
        """Pre-load a subscription row (for tests asserting status sync)."""
        with self._lock:
            self._subscriptions[subscription_id] = {
                "id": subscription_id,
                "team_id": team_id,
                "plan": plan,
                "status": "active",
                "current_period_start": _now_iso(),
                "current_period_end": _now_iso(),
                "cancel_at_period_end": False,
                "items": [{"price": {"id": f"price_{plan}"}}],
            }

    @property
    def sessions(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return dict(self._sessions)

    @property
    def events(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return dict(self._events)

    @property
    def webhook_secret(self) -> str:
        return self._webhook_secret


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
