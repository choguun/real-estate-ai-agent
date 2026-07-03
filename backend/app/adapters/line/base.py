"""LINE adapter Protocol + HMAC-SHA256 sign/verify helpers.

LINE's webhook auth scheme: a header `X-Line-Signature` carries a
base64(HMAC-SHA256(channel_secret, raw_request_body)). Verifying the
signature against the raw bytes (BEFORE JSON parsing) is the single
thing that prevents spoofed events.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Protocol, runtime_checkable

SIGNATURE_HEADER = "X-Line-Signature"


def sign_line_webhook(body: bytes, channel_secret: str) -> str:
    """base64(HMAC-SHA256(secret, body)) — what LINE itself produces."""
    digest = hmac.new(
        channel_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def verify_line_webhook(body: bytes, signature: str | None, channel_secret: str) -> bool:
    """Constant-time compare. Returns False on any mismatch or missing signature."""
    if not isinstance(signature, str) or not signature:
        return False
    expected = sign_line_webhook(body, channel_secret)
    try:
        return hmac.compare_digest(expected.encode("ascii"), signature.encode("ascii"))
    except (UnicodeDecodeError, AttributeError):
        return False


@runtime_checkable
class LineAdapter(Protocol):
    """LINE messaging adapter — mock + real (stub for MVP)."""

    @property
    def channel_secret(self) -> str: ...

    def sign(self, body: bytes) -> str:
        """Sign `body` with the channel secret. Used by tests/dev tooling."""
        ...

    def verify(self, body: bytes, signature: str) -> bool:
        """Verify a request signature. Returns False on any mismatch."""
        ...
