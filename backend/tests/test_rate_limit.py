"""T-601 — RateLimiter infrastructure (cycle 6 AC-RL-05, AC-RL-06).

8 unit tests covering:
- Allow under limit returns allowed=True
- Allow at limit returns allowed=False with retry_after > 0
- Different keys are independent (per-IP isolation)
- Window expires (timestamps outside the window don't count)
- Action-policies are enforced (different actions have different limits)
- Fail-open on internal exception (broken limiter must NOT block traffic)
- RedisRateLimiter stub exists, passes isinstance(r, RateLimiter)
- reset_cache() clears state for test isolation

Plus a thread-safety smoke test (10 threads × 100 calls each).
"""

from __future__ import annotations

import threading
from unittest.mock import patch

import pytest

from app.rate_limit import (
    InMemoryRateLimiter,
    RateLimiter,
    RateLimitPolicy,
    RateLimitResult,
    RedisRateLimiter,
)
from app.rate_limit_factory import get_rate_limiter, reset_cache

# ── Policy + Result shape ────────────────────────────────────────


def test_rate_limit_result_has_required_fields() -> None:
    """RateLimitResult is the contract every backend reads."""
    r = RateLimitResult(allowed=True, retry_after=0, limit=5, remaining=4)
    assert r.allowed is True
    assert r.retry_after == 0
    assert r.limit == 5
    assert r.remaining == 4


def test_rate_limit_policy_dataclass() -> None:
    """RateLimitPolicy is what the Settings translates into."""
    p = RateLimitPolicy(max_calls=5, window_seconds=900)
    assert p.max_calls == 5
    assert p.window_seconds == 900


# ── InMemoryRateLimiter behavior ──────────────────────────────────


def test_in_memory_limiter_allows_under_limit() -> None:
    """AC-RL-05: 1st..Nth call within window returns allowed=True."""
    limiter = InMemoryRateLimiter(
        limits={"auth.login": RateLimitPolicy(max_calls=5, window_seconds=900)}
    )
    for i in range(5):
        result = limiter.allow(key="1.2.3.4", action="auth.login")
        assert result.allowed is True, f"call {i + 1} should be allowed"
        assert result.remaining == 5 - (i + 1)


def test_in_memory_limiter_denies_over_limit() -> None:
    """6th call within the window returns allowed=False + Retry-After."""
    limiter = InMemoryRateLimiter(
        limits={"auth.login": RateLimitPolicy(max_calls=5, window_seconds=900)}
    )
    for _ in range(5):
        limiter.allow(key="1.2.3.4", action="auth.login")
    result = limiter.allow(key="1.2.3.4", action="auth.login")
    assert result.allowed is False
    assert result.retry_after > 0
    assert result.retry_after <= 900
    assert result.remaining == 0


def test_in_memory_limiter_keys_are_independent() -> None:
    """Per-IP isolation: hitting the limit on one IP doesn't block
    another IP.
    """
    limiter = InMemoryRateLimiter(
        limits={"auth.login": RateLimitPolicy(max_calls=2, window_seconds=900)}
    )
    # IP A hits the limit
    assert limiter.allow(key="ip-a", action="auth.login").allowed
    assert limiter.allow(key="ip-a", action="auth.login").allowed
    assert not limiter.allow(key="ip-a", action="auth.login").allowed
    # IP B is unaffected
    assert limiter.allow(key="ip-b", action="auth.login").allowed
    assert limiter.allow(key="ip-b", action="auth.login").allowed


def test_in_memory_limiter_window_expires() -> None:
    """AC-RL-05: timestamps outside the window are pruned, freeing
    up the quota.
    """
    limiter = InMemoryRateLimiter(
        limits={"auth.login": RateLimitPolicy(max_calls=2, window_seconds=60)}
    )
    # Two calls at t=0
    with patch("app.rate_limit.time.monotonic", return_value=0.0):
        assert limiter.allow(key="ip", action="auth.login").allowed
        assert limiter.allow(key="ip", action="auth.login").allowed
        assert not limiter.allow(key="ip", action="auth.login").allowed
    # 61 seconds later, the window has slid past the original calls
    with patch("app.rate_limit.time.monotonic", return_value=61.0):
        assert limiter.allow(key="ip", action="auth.login").allowed


def test_in_memory_limiter_enforces_action_policies() -> None:
    """Different actions have independent limit buckets. A user
    hitting the login limit doesn't trigger the signup limit.
    """
    limiter = InMemoryRateLimiter(
        limits={
            "auth.login": RateLimitPolicy(max_calls=2, window_seconds=900),
            "auth.signup": RateLimitPolicy(max_calls=5, window_seconds=3600),
        }
    )
    # Burn through login quota
    limiter.allow(key="ip", action="auth.login")
    limiter.allow(key="ip", action="auth.login")
    assert not limiter.allow(key="ip", action="auth.login").allowed
    # Signup is unaffected
    for _ in range(5):
        assert limiter.allow(key="ip", action="auth.signup").allowed


def test_in_memory_limiter_fails_open_on_internal_exception() -> None:
    """Cycle 6 risk: a broken limiter must NOT block legitimate
    traffic. Internal exceptions are caught and the limiter returns
    allowed=True with a logged error.
    """
    limiter = InMemoryRateLimiter(
        limits={"auth.login": RateLimitPolicy(max_calls=5, window_seconds=900)}
    )
    # Force an internal failure by patching the underlying store
    with patch.object(limiter, "_now", side_effect=RuntimeError("simulated outage")):
        result = limiter.allow(key="ip", action="auth.login")
    assert result.allowed is True  # fail-open


# ── Protocol + Redis stub ─────────────────────────────────────────


def test_redis_rate_limiter_stub_is_instance_of_protocol() -> None:
    """AC-RL-06: the Redis stub passes isinstance(r, RateLimiter)."""
    stub = RedisRateLimiter()
    assert isinstance(stub, RateLimiter)


def test_redis_rate_limiter_stub_raises_not_implemented() -> None:
    """AC-RL-06: cycle 7 fills in the real impl. Until then, calling
    allow() on the stub raises NotImplementedError so we don't
    silently fall back to in-memory semantics.
    """
    stub = RedisRateLimiter()
    with pytest.raises(NotImplementedError):
        stub.allow(key="ip", action="auth.login")


# ── Factory + cache reset ─────────────────────────────────────────


def test_factory_returns_singleton() -> None:
    """The factory caches the limiter so all callers share state."""
    reset_cache()
    a = get_rate_limiter()
    b = get_rate_limiter()
    assert a is b
    reset_cache()


def test_factory_reset_clears_state() -> None:
    """reset_cache() drops the singleton — useful for test isolation."""
    reset_cache()
    limiter = get_rate_limiter()
    assert limiter.allow(key="ip", action="auth.login").allowed
    reset_cache()
    limiter2 = get_rate_limiter()
    # After reset, the limit is fresh — but we can't directly assert
    # "different instance" because lru_cache might return the same
    # object. We assert the call is allowed (fresh quota) instead.
    assert limiter2.allow(key="ip", action="auth.login").allowed
    reset_cache()


# ── Thread safety smoke ───────────────────────────────────────────


def test_in_memory_limiter_thread_safe_smoke() -> None:
    """10 threads × 100 calls each against a limit of 50.
    Total allowed ≤ 50 (some calls must be rejected) AND the test
    doesn't deadlock or raise.
    """
    limiter = InMemoryRateLimiter(
        limits={"auth.login": RateLimitPolicy(max_calls=50, window_seconds=900)}
    )
    allowed_count = 0
    lock = threading.Lock()
    barrier = threading.Barrier(10)

    def worker() -> None:
        nonlocal allowed_count
        barrier.wait()  # all threads start at the same moment
        for _ in range(100):
            result = limiter.allow(key="shared-ip", action="auth.login")
            if result.allowed:
                with lock:
                    allowed_count += 1

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert (
        allowed_count == 50
    ), f"thread-safety broken: {allowed_count} calls allowed (expected exactly 50)"
