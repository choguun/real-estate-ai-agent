"""Rate-limiter factory — cycle 6 T-601.

Builds the rate limiter from Settings. Cycle 6 returns the
in-memory implementation. Cycle 7 will swap in Redis when
USE_REDIS_RATE_LIMIT=true (or similar) without touching call sites.

The factory is `@lru_cache`'d so all callers share state within a
process. Tests call `reset_cache()` to start with fresh state.
"""

from __future__ import annotations

from functools import lru_cache

from app.config import Settings, get_settings
from app.rate_limit import InMemoryRateLimiter, RateLimiter, RateLimitPolicy


@lru_cache(maxsize=1)
def _build(
    rate_limit_login_per_15min: int,
    rate_limit_signup_per_hour: int,
    rate_limit_invite_per_hour: int,
) -> RateLimiter:
    """Build the in-memory rate limiter with policies from Settings.

    Takes primitives (not Settings) so lru_cache can hash them.
    """
    return InMemoryRateLimiter(
        limits={
            "auth.login": RateLimitPolicy(
                max_calls=rate_limit_login_per_15min,
                window_seconds=15 * 60,
            ),
            "auth.signup": RateLimitPolicy(
                max_calls=rate_limit_signup_per_hour,
                window_seconds=60 * 60,
            ),
            "team.invite": RateLimitPolicy(
                max_calls=rate_limit_invite_per_hour,
                window_seconds=60 * 60,
            ),
        }
    )


def get_rate_limiter(settings: Settings | None = None) -> RateLimiter:
    """Return the cached RateLimiter singleton.

    Pass `settings` for explicit injection (tests); otherwise the
    global `get_settings()` is used.
    """
    s = settings or get_settings()
    return _build(
        rate_limit_login_per_15min=s.rate_limit_login_per_15min,
        rate_limit_signup_per_hour=s.rate_limit_signup_per_hour,
        rate_limit_invite_per_hour=s.rate_limit_invite_per_hour,
    )


def reset_cache() -> None:
    """Drop the cached singleton — useful for test isolation."""
    _build.cache_clear()
