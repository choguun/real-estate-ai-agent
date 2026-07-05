"""T-701 — Redis-backed rate limiter (cycle 7 AC-DRL-01..06).

8 tests covering the real Redis impl (replaces cycle-6's stub):

- Allow under limit returns allowed=True
- Allow at limit returns allowed=False with retry_after > 0
- Different keys are independent (per-IP isolation across pods)
- Window expires (timestamps outside the window don't count)
- Action-policies are enforced (different actions have different limits)
- Fail-open on Redis error (Redis outage must NOT block traffic)
- EXPIRE TTL is set on every key (memory bounding)
- RedisRateLimiter satisfies isinstance(r, RateLimiter)

Uses `fakeredis` for hermetic in-process testing (no real Redis
required). The real `redis-py` client is exercised in cycle-8's
integration tests against a real Redis instance.
"""

from __future__ import annotations

from unittest.mock import patch

import fakeredis
import pytest

from app.rate_limit import (
    RateLimiter,
    RateLimitPolicy,
)
from app.redis_rate_limiter import RedisRateLimiter


@pytest.fixture
def fake_redis() -> fakeredis.FakeRedis:
    """In-process Redis substitute. Supports sorted sets + TTL."""
    return fakeredis.FakeRedis()


# ── Protocol conformance ──────────────────────────────────────────


def test_redis_rate_limiter_is_instance_of_protocol(fake_redis: fakeredis.FakeRedis) -> None:
    """AC-DRL-01: the real impl satisfies isinstance(r, RateLimiter)."""
    limiter = RedisRateLimiter(
        redis_client=fake_redis,
        limits={"auth.login": RateLimitPolicy(max_calls=5, window_seconds=900)},
    )
    assert isinstance(limiter, RateLimiter)


# ── Allow / deny ──────────────────────────────────────────────────


def test_redis_limiter_allows_under_limit(fake_redis: fakeredis.FakeRedis) -> None:
    """AC-DRL-01: 1st..Nth call within window returns allowed=True."""
    limiter = RedisRateLimiter(
        redis_client=fake_redis,
        limits={"auth.login": RateLimitPolicy(max_calls=5, window_seconds=900)},
    )
    for i in range(5):
        result = limiter.allow(key="1.2.3.4", action="auth.login")
        assert result.allowed is True, f"call {i+1} should be allowed"
        assert result.remaining == 5 - (i + 1)


def test_redis_limiter_denies_over_limit(fake_redis: fakeredis.FakeRedis) -> None:
    """AC-DRL-01: 6th call within the window returns allowed=False."""
    limiter = RedisRateLimiter(
        redis_client=fake_redis,
        limits={"auth.login": RateLimitPolicy(max_calls=5, window_seconds=900)},
    )
    for _ in range(5):
        limiter.allow(key="1.2.3.4", action="auth.login")
    result = limiter.allow(key="1.2.3.4", action="auth.login")
    assert result.allowed is False
    assert result.retry_after > 0
    assert result.retry_after <= 900
    assert result.remaining == 0


# ── Isolation + window ───────────────────────────────────────────


def test_redis_limiter_keys_are_independent(fake_redis: fakeredis.FakeRedis) -> None:
    """Multi-pod isolation: per-key buckets don't interfere."""
    limiter = RedisRateLimiter(
        redis_client=fake_redis,
        limits={"auth.login": RateLimitPolicy(max_calls=2, window_seconds=900)},
    )
    # IP A hits the limit
    assert limiter.allow(key="ip-a", action="auth.login").allowed
    assert limiter.allow(key="ip-a", action="auth.login").allowed
    assert not limiter.allow(key="ip-a", action="auth.login").allowed
    # IP B is unaffected
    assert limiter.allow(key="ip-b", action="auth.login").allowed
    assert limiter.allow(key="ip-b", action="auth.login").allowed


def test_redis_limiter_window_expires(fake_redis: fakeredis.FakeRedis) -> None:
    """AC-DRL-04: timestamps outside the window are pruned."""
    limiter = RedisRateLimiter(
        redis_client=fake_redis,
        limits={"auth.login": RateLimitPolicy(max_calls=2, window_seconds=60)},
    )
    # Two calls at t=0
    with patch("app.redis_rate_limiter.time.time", return_value=0.0):
        assert limiter.allow(key="ip", action="auth.login").allowed
        assert limiter.allow(key="ip", action="auth.login").allowed
        assert not limiter.allow(key="ip", action="auth.login").allowed
    # 61 seconds later, the window has slid past the original calls
    with patch("app.redis_rate_limiter.time.time", return_value=61.0):
        assert limiter.allow(key="ip", action="auth.login").allowed


def test_redis_limiter_enforces_action_policies(fake_redis: fakeredis.FakeRedis) -> None:
    """Different actions have independent limit buckets."""
    limiter = RedisRateLimiter(
        redis_client=fake_redis,
        limits={
            "auth.login": RateLimitPolicy(max_calls=2, window_seconds=900),
            "auth.signup": RateLimitPolicy(max_calls=5, window_seconds=3600),
        },
    )
    # Burn through login quota
    limiter.allow(key="ip", action="auth.login")
    limiter.allow(key="ip", action="auth.login")
    assert not limiter.allow(key="ip", action="auth.login").allowed
    # Signup is unaffected
    for _ in range(5):
        assert limiter.allow(key="ip", action="auth.signup").allowed


# ── Fail-open + TTL ──────────────────────────────────────────────


def test_redis_limiter_fails_open_on_redis_error(fake_redis: fakeredis.FakeRedis) -> None:
    """AC-DRL-05: a Redis outage MUST NOT block legitimate traffic.

    The cycle-6 fail-open contract applies to RedisRateLimiter
    too: if redis_client raises (connection timeout, auth failure,
    OOM), the limiter returns allowed=True and logs the error.
    """
    limiter = RedisRateLimiter(
        redis_client=fake_redis,
        limits={"auth.login": RateLimitPolicy(max_calls=5, window_seconds=900)},
    )
    # Force every Redis call to raise
    fake_redis.zadd = lambda *a, **kw: (_ for _ in ()).throw(
        ConnectionError("simulated Redis outage")
    )
    result = limiter.allow(key="ip", action="auth.login")
    assert result.allowed is True  # fail-open


def test_redis_limiter_sets_expire_ttl(fake_redis: fakeredis.FakeRedis) -> None:
    """AC-DRL-04: every key has EXPIRE = window_seconds + 60s buffer
    so memory is bounded even for IPs that never come back.

    The +60s buffer gives slack against clock skew + script
    execution time, so the key doesn't expire mid-window.
    """
    limiter = RedisRateLimiter(
        redis_client=fake_redis,
        limits={"auth.login": RateLimitPolicy(max_calls=5, window_seconds=900)},
    )
    limiter.allow(key="ip", action="auth.login")
    # fakeredis exposes TTL on the key
    ttl = fake_redis.ttl("rl:auth.login:ip")
    # TTL should be > 0 (set) and <= window + buffer
    assert 0 < ttl <= 900 + 60, f"expected TTL ≤ 960s, got {ttl}"


def test_redis_limiter_unknown_action_allows_through(fake_redis: fakeredis.FakeRedis) -> None:
    """Defensive: an action not in the policy map is allowed (so a
    future action that forgot to register doesn't accidentally
    rate-limit all traffic to zero). Mirrors InMemoryRateLimiter.
    """
    limiter = RedisRateLimiter(
        redis_client=fake_redis,
        limits={"auth.login": RateLimitPolicy(max_calls=5, window_seconds=900)},
    )
    result = limiter.allow(key="ip", action="auth.unknown_action")
    assert result.allowed is True
    assert result.limit == 0
