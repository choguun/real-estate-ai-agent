# Spec: Cycle 7 — Operational Security Polish

> **Status:** specifying
> **Branch:** `feat/cycle-7-operational-polish`
> **Cycle origin:** Cycle-6 review P2 warnings + cycle-6/cycle-5
> "Out of Scope" → cycle-7 items.

---

## Objective

Cycles 5 + 6 closed the big security footguns (insecure defaults,
audit log, rate limiting, secret rotation, front-end headers).
Cycle 7 polishes what's left: distributed (multi-pod) rate limiting,
per-team rate-limit thresholds, and CSP violation reporting.

These are the three cycle-7 candidates that **don't require new
schema** (no migration pain) but **unblock production deploy** in
ways the cycle-6 work alone doesn't:

1. **Distributed rate limiting** — the `InMemoryRateLimiter` from
   cycle-6 only works in single-process deploys. Multi-pod
   Railway / Fly / Render deploys need a Redis backend so the
   limit is consistent across pods. Cycle-6 already shipped a
   `RedisRateLimiter` stub; cycle-7 fills it in.
2. **Per-team rate-limit thresholds** — today every team shares
   the same 5/15min login cap. A power-user team should be able
   to opt into stricter limits; an enterprise team should be
   able to opt into looser ones. New schema + a small admin API.
3. **CSP violation reporting** — replaces the `'unsafe-inline'`
   compromise in cycle-6's CSP with a report-uri endpoint. Today
   any XSS attempt is silently blocked; cycle-7 surfaces the
   attempts so an ops dashboard can alert.

**Who the user is:** the Thai real-estate agency from cycles 1-6,
plus any team admin who wants to tune their team's security
posture. Multi-pod deploys are the trigger for #1; #2 is a product
gap; #3 is the security polish from cycle-6's review.

**Success = after cycle 7 ships:**

```bash
# 1. Multi-pod deploy: each pod's Redis-backed limiter shares
#    state via the shared Redis instance. Brute-force on pod A
#    is rate-limited on pod B (no per-pod whitelist bypass).
for i in {1..20}; do curl -X POST /api/auth/login -d '...'; done
# → first 5 fail normally; 6th-20th return 429, regardless of
#   which pod handles the request.

# 2. Team admin sets per-team rate limits
curl -X PATCH /api/teams/{id}/rate_limits \
    -H "Authorization: Bearer $OWNER_TOK" \
    -d '{"login_per_15min": 10, "signup_per_hour": 10}'
# → team's stricter limit takes effect immediately; future
#   logins use the new threshold.

# 3. CSP violations are reported
curl -X POST /api/csp-report \
    -H "Content-Type: application/csp-report" \
    -d '{"csp-report": {"violated-directive": "script-src 'self'", ...}}'
# → lands in security_events with action='csp.violation',
#   metadata.violated_directive set so an ops dashboard can
#   alert on new violation types.
```

**Out of scope (explicit):**
- **MFA / 2FA / WebAuthn** — cycle 8 (biggest product gap; deferred
  per cycle-5 spec). The cycle-7 audit log already lays the
  groundwork (TOTP-failed events will slot into the same
  `security_events` table).
- **One-shot JWT rotation tool** — cycle 8 (the manual 4-step
  playbook in `docs/security.md` works; a proper one-shot tool
  is a polish item).
- **GDPR data export / right-to-delete** — cycle 8+ (separate
  product scope).
- **OAuth provider integration** — out of scope.

---

## Commands

```bash
# New tests
cd backend
pytest tests/test_redis_rate_limit.py tests/test_team_rate_limits.py tests/test_csp_report.py -v

# Full regression
pytest -p no:randomly  # 368 → ~400+ tests

# Lint / format / types
ruff check app tests
ruff format --check app tests
mypy app

# Frontend tests (CSP reporting client)
cd ../web
npm test -- --run
```

---

## Project Structure

```
backend/
  app/
    rate_limit.py                  # MOD: add `now()` for time injection
    redis_rate_limiter.py          # NEW: production Redis impl
    rate_limit_factory.py          # MOD: env-driven adapter selection
    config.py                      # MOD: add rate_limit_backend
                                   #      + new per-team threshold fields
    deps.py                        # MOD: RateLimitSettingsDep
    domain/team.py                 # MOD: add TeamRateLimits sub-model
    routers/
      teams.py                     # MOD: PATCH /api/teams/{id}/rate_limits
      csp_report.py                # NEW: POST /api/csp-report
    audit_log.py                   # MOD: ACTION_CSP_VIOLATION constant
    services/
      team_service.py              # MOD: get/set per-team rate limits
  migrations/
    006_team_rate_limits.sql       # NEW: team_rate_limits table + RLS
  tests/
    test_redis_rate_limit.py       # NEW: 8 tests (uses fakeredis)
    test_team_rate_limits.py       # NEW: 8 tests (CRUD + enforcement)
    test_csp_report.py             # NEW: 4 tests (parsing + audit row)

web/
  lib/
    csp_report.ts                  # NEW: client-side helper that
                                   #      sends violation reports
  __tests__/
    csp_report.test.ts             # NEW: 3 tests
  next.config.mjs                  # MOD: add report-uri directive

docs/
  security.md                      # MOD: cycle-7 addendum (Redis ops,
                                   #      per-team limits, CSP reporting)
```

---

## Code Style

Cycle-7 follows the cycle-5/6 patterns: thin Protocols + glue +
the same audit-log + DI plumbing.

**Good example (Redis rate limiter):**

```python
# app/redis_rate_limiter.py
class RedisRateLimiter:
    """Sliding-window rate limiter backed by Redis sorted sets.

    For each (key, action) pair, ZADD the timestamp, ZREMRANGEBYSCORE
    the expired entries, ZCARD to count. The key has a TTL of
    window_seconds so memory is bounded.
    """
    def __init__(self, *, redis_client: Redis, limits: dict[str, RateLimitPolicy]) -> None:
        self._redis = redis_client
        self._limits = limits

    def allow(self, *, key: str, action: str) -> RateLimitResult:
        # ... ZADD/ZREMRANGEBYSCORE pipeline; fail-open if Redis is down
```

**Good example (per-team overrides):**

```python
# app/services/team_service.py
def get_effective_rate_limits(
    adapter: SupabaseAdapter, *, team_id: UUID, defaults: RateLimits
) -> RateLimits:
    """Return the team's effective rate limits, falling back to defaults.

    A team that hasn't configured overrides gets the system defaults.
    A team that has gets its overrides merged over the defaults.
    """
```

**Good example (CSP report endpoint):**

```python
# app/routers/csp_report.py
@router.post("/csp-report")
async def csp_report(request: Request) -> dict[str, str]:
    """Receive a CSP violation report from the browser.

    Browser sends Content-Type: application/csp-report with a
    JSON body of the form {"csp-report": {...}}. We extract the
    violated-directive + blocked-uri, log an audit row, and return
    204 No Content so the browser doesn't retry.
    """
```

---

## Testing Strategy

- **Redis rate limiter (8 tests)** — uses `fakeredis` to simulate
  Redis in-process. Sliding window, multiple keys, action policies,
  fail-open on Redis outage, EXPIRE TTL, idempotency.
- **Per-team rate limits (8 tests)** — CRUD on the new endpoint +
  rate-limit-enforcement-after-override tests + admin-only check.
- **CSP report (4 tests)** — accepts the standard
  `application/csp-report` content-type, parses + extracts the
  violated directive + blocked URI, writes audit row with
  action='csp.violation'.
- **Regression**: full 368-test suite stays green.
- **Coverage**: ≥ 90% preserved.

---

## Boundaries

**Always do:**
- Run `pytest -p no:randomly` before committing
- Cycle-6's fail-open contract applies to `RedisRateLimiter` too:
  a Redis outage must NOT block traffic; the limiter returns
  `allowed=True` and logs `rate_limit redis unavailable`
- New tests fail first (RED), then minimal code (GREEN), then
  refactor
- Audit failures (Redis write failure on the audit row) are
  swallowed (write_event catches + logs)

**Ask first:**
- Adding a new dep (`fakeredis`, `redis-py`)
- Changing `Settings` field types or names
- Touching `migrations/001_init.sql` (cycle 1, frozen)

**Never do:**
- Block the primary request when Redis is unreachable (fail-open)
- Make the CSP-report endpoint require auth (browsers can't
  send auth headers; this must be open + cheap)
- Use the same Redis client for rate-limit state and the rest
  of the app (separate keyspace prefix `rl:`)
- Store per-team overrides in `redis` (they go in Supabase like
  all team-scoped data)

---

## Acceptance Criteria

### Distributed rate limiting (Redis)

- [ ] **AC-DRL-01** — `RedisRateLimiter` (real impl, not stub) ships
      and passes `isinstance(r, RateLimiter)`.
- [ ] **AC-DRL-02** — `Settings.rate_limit_backend: str = "memory"`
      default; `"redis"` selects the Redis impl.
- [ ] **AC-DRL-03** — When `rate_limit_backend=redis`, the factory
      builds `RedisRateLimiter` reading `REDIS_URL` from Settings.
- [ ] **AC-DRL-04** — Redis backend uses sorted sets
      (`ZADD timestamp`, `ZREMRANGEBYSCORE expired`, `ZCARD` count)
      with `EXPIRE = window_seconds` for memory bounding.
- [ ] **AC-DRL-05** — Redis backend fails-open if the Redis client
      raises (logs `rate_limit redis unavailable`, returns
      `allowed=True`).
- [ ] **AC-DRL-06** — 8 tests pass via `fakeredis`.

### Per-team rate-limit thresholds

- [ ] **AC-TRL-01** — `migrations/006_team_rate_limits.sql` adds
      a `team_rate_limits` table with columns `team_id PRIMARY
      KEY, login_per_15min, signup_per_hour, invite_per_hour,
      updated_at`. RLS: SELECT/UPDATE for owner of the team.
- [ ] **AC-TRL-02** — `GET /api/teams/{id}/rate_limits` returns the
      team's effective limits (override or system default).
- [ ] **AC-TRL-03** — `PATCH /api/teams/{id}/rate_limits` accepts
      `{login_per_15min?, signup_per_hour?, invite_per_hour?}`
      and updates the team's overrides. Owner only.
- [ ] **AC-TRL-04** — When a team has overrides, the rate limiter
      uses the team's limits instead of the system defaults.
- [ ] **AC-TRL-05** — Per-team override must be ≥ 1 (no negative
      or zero; cycle-7 validators).
- [ ] **AC-TRL-06** — 8 tests pass: CRUD, enforcement, admin-only,
      defaults-fallback.

### CSP violation reporting

- [ ] **AC-CSP-01** — `POST /api/csp-report` accepts the standard
      `application/csp-report` content-type and parses the
      `csp-report` JSON body.
- [ ] **AC-CSP-02** — The endpoint extracts `violated-directive`
      + `blocked-uri` and writes one row to `security_events` with
      `action='csp.violation'`, `metadata={'violated_directive':
      ..., 'blocked_uri': ...}`.
- [ ] **AC-CSP-03** — The endpoint returns `204 No Content` (the
      browser doesn't retry on 204) and never raises on
      malformed bodies (logs + 204).
- [ ] **AC-CSP-04** — `web/next.config.mjs` adds
      `report-uri /api/csp-report` to the CSP header in production.
- [ ] **AC-CSP-05** — 4 backend tests + 3 frontend tests pass.

### Docs + regression

- [ ] **AC-DOC-01** — `docs/security.md` adds a cycle-7 addendum
      covering Redis ops (provisioning the Redis URL, monitoring
      Redis latency), per-team admin guide, CSP reporting ops.
- [ ] **AC-REG-01** — All 368 existing tests still pass.
- [ ] **AC-REG-02** — `pytest -p no:randomly` reports ≥ 388 tests
      (368 + ~20 new), ≥ 90% coverage.
- [ ] **AC-REG-03** — `ruff check` + `ruff format --check` + `mypy
      app/` all clean.
- [ ] **AC-REG-04** — `npm run typecheck` + `npm test` clean.

---

## Out of Scope

- **MFA / 2FA / WebAuthn** — cycle 8 (biggest product gap; deferred
  per cycle-5 spec)
- **One-shot JWT secret rotation tool** — cycle 8 (the manual
  4-step playbook in `docs/security.md` works)
- **GDPR data export / right-to-delete** — cycle 8+ (separate
  product scope)
- **OAuth provider integration** — out of scope
- **CSP nonce-based upgrade** — cycle 8+ (the report-uri in cycle 7
  collects the data needed to make nonce-based safe)

---

## Open Questions

1. **Q: Should the per-team rate limits be a separate `Settings`
   row, or stored in the `teams` table?** Recommend: **separate
   `team_rate_limits` table** with a `team_id PRIMARY KEY` FK
   to `teams`. A team without overrides is a row-less lookup
   that falls back to the system defaults. Mirrors the
   cycle-4 `billing_customers` pattern.

2. **Q: For `RedisRateLimiter`, should we use `redis.asyncio`
   (async) or `redis` (sync)?** Recommend: **sync**, wrapped
   in `asyncio.to_thread` if the call site is async. Simpler
   + easier to test + matches the cycle-6 sync signature
   (`RateLimiter.allow` returns `RateLimitResult`, no await).

3. **Q: For the CSP-report endpoint, should the audit row be
   rate-limited?** A misbehaving browser could spam reports.
   Recommend: **yes**, with a generous bucket (1000/hour per
   IP) so a real attack surfaces in audit but a misconfigured
   extension doesn't 429 the page. Cycle-8 polish.

4. **Q: Should the per-team PATCH return the new effective
   limits or just 204?** Recommend: **return the new effective
   limits**. Admin endpoints that return state make UIs simpler.

5. **Q: Does cycle-7 close the cycle-6 P2 warnings about
   `event_action: Literal[...]`, autouse fixture redundancy,
   `decode_token()` rename, rotation rollback?** Recommend:
   **no, defer to cycle 8**. Those are cosmetic. Cycle 7's
   scope is "operational polish" not "polish everything".