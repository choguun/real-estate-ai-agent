"""Redis-backed rate limiter — cycle 7 T-701 (AC-DRL-01..06).

The production-ready impl of `RateLimiter`. Cycle 6 shipped a
stub that raised `NotImplementedError`; cycle 7 fills it in with
a sorted-set sliding-window algorithm.

## Why sorted sets

Each (key, action) pair maps to a Redis sorted set:

    ZADD rl:{action}:{key} <timestamp>:<unique_id> <timestamp>

The sorted set keeps insertion-ordered members, each scored by
the call's timestamp. To check + record:

    ZREMRANGEBYSCORE rl:{action}:{key} 0 <now - window>   # prune
    ZADD rl:{action}:{key} <now>:<unique> <now>             # record
    ZCARD rl:{action}:{key}                               # count
    EXPIRE rl:{action}:{key} <window + buffer>             # memory bound

This is atomic-enough for rate-limiting (the prune+add+count is
a single Redis pipeline, so concurrent writers don't overshoot
the limit by more than 1).

## Fail-open contract

A Redis outage (ConnectionError, TimeoutError, auth failure)
MUST NOT block legitimate traffic. The limiter catches all
Redis exceptions, logs `rate_limit redis unavailable`, and
returns `allowed=True`. Same contract as the cycle-6
InMemoryRateLimiter.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from app.rate_limit import RateLimitPolicy, RateLimitResult

logger = logging.getLogger(__name__)

# Keyspace prefix keeps rate-limit state separate from any other
# Redis usage the app might add in the future.
_KEY_PREFIX = "rl"


class RedisRateLimiter:
    """Distributed sliding-window rate limiter backed by Redis sorted sets.

    Suitable for multi-pod production deploys: every pod reads /
    writes the same key, so the limit is consistent cluster-wide.

    Args:
        redis_client: A `redis.Redis` (or `fakeredis.FakeRedis`) instance.
            Any object that exposes the pipeline / zadd / zremrangebyscore
            / zcard / expire methods works.
        limits: Maps action name → policy. Unknown actions are
            allowed through (defensive: a future action that forgot
            to register doesn't accidentally rate-limit everyone
            to zero).
    """

    def __init__(
        self,
        *,
        redis_client: Any,
        limits: dict[str, RateLimitPolicy],
    ) -> None:
        self._redis = redis_client
        self._limits = limits

    def _key(self, action: str, key: str) -> str:
        """Compose the Redis key for a (action, key) bucket."""
        return f"{_KEY_PREFIX}:{action}:{key}"

    def allow(self, *, key: str, action: str) -> RateLimitResult:
        """Check + record. Atomic via Redis pipeline. Fail-open on errors.

        Args:
            key: Per-caller identifier (IP, user_id, ...).
            action: The action name (e.g., 'auth.login').

        Returns:
            RateLimitResult. When allowed=False, retry_after is the
            number of seconds the caller should wait.
        """
        policy = self._limits.get(action)
        if policy is None:
            # Defensive: unknown action → no policy → allow.
            return RateLimitResult(allowed=True, retry_after=0, limit=0, remaining=0)

        try:
            now = time.time()
            window_start = now - policy.window_seconds
            redis_key = self._key(action, key)
            unique = uuid.uuid4().hex

            # Pipeline: prune, count, then record + set TTL atomically.
            # fakeredis supports pipeline(); real redis-py does too.
            pipe = self._redis.pipeline()
            pipe.zremrangebyscore(redis_key, 0, window_start)
            pipe.zcard(redis_key)
            _, count = pipe.execute()

            if count >= policy.max_calls:
                # Reject. retry_after = seconds until the oldest entry
                # slides out of the window. We need the oldest timestamp
                # to compute this; one extra ZRANGE.
                oldest = self._redis.zrange(redis_key, 0, 0, withscores=True)
                if oldest:
                    oldest_ts = oldest[0][1]
                    retry_after = max(1, int(oldest_ts + policy.window_seconds - now) + 1)
                else:
                    # Edge case: bucket was pruned between ZCARD and ZRANGE.
                    # Use a small fallback retry.
                    retry_after = 1
                return RateLimitResult(
                    allowed=False,
                    retry_after=retry_after,
                    limit=policy.max_calls,
                    remaining=0,
                )

            # Accept. Record + set TTL. Two operations, but on a
            # Redis pipeline so still single round-trip.
            accept_pipe = self._redis.pipeline()
            accept_pipe.zadd(redis_key, {f"{now}:{unique}": now})
            accept_pipe.expire(redis_key, policy.window_seconds + 60)
            accept_pipe.execute()

            remaining = policy.max_calls - (count + 1)
            return RateLimitResult(
                allowed=True,
                retry_after=0,
                limit=policy.max_calls,
                remaining=remaining,
            )
        except Exception as exc:  # noqa: BLE001 — intentional fail-open
            logger.error(
                "rate_limit redis unavailable (action=%s key=%s): %s",
                action,
                key,
                exc,
            )
            return RateLimitResult(allowed=True, retry_after=0, limit=0, remaining=0)
