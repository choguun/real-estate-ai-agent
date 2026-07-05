"""Rate limiter — cycle 6 T-601 (AC-RL-05, AC-RL-06).

A small, thread-safe sliding-window rate limiter. Two implementations
behind one Protocol:

- `InMemoryRateLimiter`: per-process state, suitable for dev / test /
  small prod (single-pod). The default for cycle 6.
- `RedisRateLimiter`: stub for cycle 7. The Protocol contract is
  defined here; the cycle-7 impl will swap it in via the factory
  without touching call sites.

Sliding-window algorithm: per `(key, action)` pair, keep a deque of
timestamps. On each `allow()` call, prune entries older than the
window, count what's left, and either accept (append + return
allowed=True) or reject (return allowed=False + retry_after).

Fail-open contract: if the limiter raises internally (corrupt
deque, future Redis call times out, etc.), `allow()` MUST return
`allowed=True` and log the error. A broken limiter never blocks
legitimate traffic.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ── Data shapes ────────────────────────────────────────────────────


@dataclass(frozen=True)
class RateLimitPolicy:
    """A limit policy: max N calls per window_seconds."""

    max_calls: int
    window_seconds: int


@dataclass(frozen=True)
class RateLimitResult:
    """The result of an `allow()` check.

    Attributes:
        allowed: True if the call should proceed.
        retry_after: Seconds until the call would be allowed (0 if
            allowed=True).
        limit: The policy's max_calls (for the X-RateLimit-Limit
            response header).
        remaining: Calls remaining in the current window (0 if
            allowed=False).
    """

    allowed: bool
    retry_after: int
    limit: int
    remaining: int


@runtime_checkable
class RateLimiter(Protocol):
    """The single interface the rest of the app uses to rate-limit."""

    def allow(self, *, key: str, action: str) -> RateLimitResult:
        """Check if `key` may perform `action` right now.

        Args:
            key: Per-caller identifier (IP, user_id, team_id+owner_id, ...).
            action: The action name (e.g., 'auth.login', 'auth.signup').

        Returns:
            RateLimitResult. When allowed=False, retry_after is the
            number of seconds the caller should wait before retrying.
        """
        ...


# ── InMemoryRateLimiter ────────────────────────────────────────────


class InMemoryRateLimiter:
    """Thread-safe sliding-window rate limiter (in-process state).

    Per `(key, action)`, keeps a deque of monotonic timestamps. On
    each `allow()`, prunes timestamps older than the window and
    checks if the remaining count is under the policy's max_calls.

    Suitable for dev, test, and single-process prod. For multi-pod
    deployments, swap in `RedisRateLimiter` via the factory.
    """

    def __init__(
        self,
        *,
        limits: dict[str, RateLimitPolicy],
        buckets: dict[tuple[str, str], deque[float]] | None = None,
    ) -> None:
        """Build the limiter with a per-action policy map.

        Args:
            limits: Maps action name → policy. Unknown actions are
                allowed through (defensive: cycle 6 ships 3 actions;
                a future action that forgot to register doesn't
                accidentally rate-limit everyone to zero).
            buckets: Optional shared buckets dict. Use this when you
                need to share sliding-window state across multiple
                `InMemoryRateLimiter` instances (cycle 7 T-702: per-
                team limiters built per-request share state via this
                dict, so a team that hits its limit on request 1
                is still rate-limited on request 2).
        """
        self._limits = limits
        self._buckets: dict[tuple[str, str], deque[float]] = (
            buckets if buckets is not None else defaultdict(deque)
        )
        self._lock = threading.RLock()

    def _now(self) -> float:
        """Return the current monotonic clock value.

        Public-ish (single underscore so tests can patch it).
        """
        return time.monotonic()

    def allow(self, *, key: str, action: str) -> RateLimitResult:
        """Check + record. Thread-safe. Fail-open on internal errors."""
        try:
            policy = self._limits.get(action)
            if policy is None:
                # Unknown action → no policy → allow. Defensive default
                # so a future action that forgot to register doesn't
                # accidentally rate-limit all traffic to zero.
                return RateLimitResult(allowed=True, retry_after=0, limit=0, remaining=0)

            now = self._now()
            window_start = now - policy.window_seconds

            with self._lock:
                bucket = self._buckets[(key, action)]
                # Prune expired entries from the left
                while bucket and bucket[0] <= window_start:
                    bucket.popleft()

                if len(bucket) >= policy.max_calls:
                    # Reject. retry_after = seconds until oldest
                    # entry slides out of the window.
                    retry_after = max(1, int(bucket[0] + policy.window_seconds - now) + 1)
                    return RateLimitResult(
                        allowed=False,
                        retry_after=retry_after,
                        limit=policy.max_calls,
                        remaining=0,
                    )

                # Accept. Append timestamp.
                bucket.append(now)
                remaining = policy.max_calls - len(bucket)
                return RateLimitResult(
                    allowed=True,
                    retry_after=0,
                    limit=policy.max_calls,
                    remaining=remaining,
                )
        except Exception as exc:  # noqa: BLE001 — intentional fail-open
            logger.error(
                "rate_limit internal error (key=%s action=%s): %s",
                key,
                action,
                exc,
            )
            return RateLimitResult(allowed=True, retry_after=0, limit=0, remaining=0)


# ── RedisRateLimiter stub ─────────────────────────────────────────


class RedisRateLimiter:
    """Cycle-7 stub. Passes `isinstance(r, RateLimiter)` but raises
    NotImplementedError on `allow()`.

    The cycle-7 impl will:
      1. Use Redis sorted sets keyed by `(action, key)`.
      2. ZADD timestamp, ZREMRANGEBYSCORE old entries, ZCARD to count.
      3. EXPIRE the key for memory-bounded storage.

    For cycle 6 we ship the Protocol + the stub so call sites can be
    written and tested against the in-memory implementation. Swapping
    in Redis is a one-line change in `rate_limit_factory.get_rate_limiter`.
    """

    def allow(self, *, key: str, action: str) -> RateLimitResult:  # pragma: no cover
        raise NotImplementedError(
            "RedisRateLimiter.allow() ships in cycle 7. "
            "Use InMemoryRateLimiter for cycle 6 (single-process)."
        )
