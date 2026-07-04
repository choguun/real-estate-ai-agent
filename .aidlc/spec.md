# Spec: Cycle 6 — Rate Limiting, Secret Rotation, Front-End Headers

> **Status:** specifying
> **Branch:** `feat/rate-limiting`
> **Cycle origin:** Cycle 5 out-of-scope (rate limiting + secret rotation
> tooling + front-end CSP/HSTS), all flagged as "cycle 6+"

---

## Objective

Cycle 5 closed the silent-footgun defaults (JWT/CORS/LINE/Stripe) and
added an audit log. Cycle 6 closes the **operational** security gaps
that remain:

1. **Rate limiting** — `/api/auth/login` is brute-forceable today
   (the `# TODO(security): add a rate limiter` comment in
   `routers/auth.py:71-72` is the smell). Add an IP-keyed sliding-
   window rate limiter, plumb it into the auth + signup +
   invitation routers, and emit audit events when limits trip.
2. **Secret rotation tooling** — operators can rotate `JWT_SECRET`
   (and other secrets) without logging every user out. The
   `validate_security()` from cycle 5 rejects new deploys but
   doesn't help on rotation day. Add a "previous-secret" env var
   that the JWT decoder tries as a fallback during the rollover
   window.
3. **Front-end security headers** — Next.js serves the dashboard
   without CSP / HSTS / X-Frame-Options / Referrer-Policy. Add
   them in `next.config.mjs` so a deployed instance gets the
   baseline headers by default.

**Who the user is:** the same Thai real-estate agency from cycles
1-5. They deploy via Railway. Cycle 5 closed "deploy with bad
config"; cycle 6 closes "operate the deploy safely."

**Success = on a fresh deploy:**

```bash
# 1. Login brute-force is rate-limited
for i in {1..20}; do curl -X POST /api/auth/login -d '...'; done
# → first 5 succeed/fail normally; 6th-20th return 429 with
#   Retry-After header. security_events captures each rejection
#   with action='auth.rate_limited'.

# 2. JWT secret rotation works without logging users out
#    Old + new secret both accepted for the rollover window
JWT_SECRET="<new>" JWT_SECRET_PREVIOUS="<old>" uvicorn app.main:app
# → tokens issued with either secret verify successfully

# 3. Front-end headers are set
curl -I https://app.example.com/
# → Content-Security-Policy, Strict-Transport-Security,
#   X-Content-Type-Options, X-Frame-Options, Referrer-Policy
```

**Out of scope (explicit):**
- MFA / 2FA / WebAuthn — cycle 7+ (requires user-profile changes)
- Distributed rate limiting (Redis-backed) — cycle 7+ (Redis is a
  new dep; cycle 6 ships in-memory with a Redis adapter stub)
- OAuth provider integration — out of scope
- GDPR data export / right-to-delete — cycle 8

---

## Commands

```bash
# Run the new tests
cd backend
pytest tests/test_rate_limit.py tests/test_secret_rotation.py -v

# Run the full suite (regression)
pytest -p no:randomly  # 343 → 365+ tests

# Lint / format / types
ruff check app tests
ruff format --check app tests
mypy app

# Front-end typecheck + tests
cd ../web
npm run typecheck
npm test
```

---

## Project Structure

```
backend/app/
  rate_limit.py              # NEW: RateLimiter Protocol + InMemoryRateLimiter
  secret_rotation.py         # NEW: rotating_secret() helper (dual-verify)
  settings_validation_helpers.py  # (folded into existing security_validation.py)
  routers/
    auth.py                  # MOD: rate-limit login + signup
    teams.py                 # MOD: rate-limit invitation POST
  tests/
    test_rate_limit.py       # NEW: 8 tests (unit + integration)
    test_secret_rotation.py  # NEW: 4 tests
    test_audit_log.py        # EXTEND: 2 tests for rate-limit audit hooks

web/
  next.config.mjs            # MOD: add CSP, HSTS, X-Frame-Options, etc.
  __tests__/
    headers.test.ts          # NEW: 3 tests asserting headers on rendered pages

docs/
  security.md                # NEW: secret rotation playbook + audit query
                             #       cookbook + incident response
                             #       (this is T-505 from cycle 5,
                             #       folded into cycle 6's T-606)
```

---

## Code Style

Cycle-6 follows the cycle-5 pattern: pure functions / Protocols,
thin glue. New rate-limit code is backend-only; new headers are a
Next.js config change.

**Good example (rate limiter):**

```python
# app/rate_limit.py
class RateLimiter(Protocol):
    def allow(self, *, key: str, action: str) -> RateLimitResult: ...

class InMemoryRateLimiter:
    """Thread-safe sliding-window rate limiter.

    Stores per-key action history in a deque, prunes old entries
    on each `allow()` call. Suitable for single-process dev / test
    / small prod; cycle 7 ships a Redis-backed adapter for multi-
    pod deployments.
    """
    def __init__(self, *, limits: dict[str, RateLimitPolicy]) -> None: ...
```

**Good example (secret rotation):**

```python
# app/secret_rotation.py
def decode_token_rotating(token: str, settings: Settings) -> dict[str, Any]:
    """Decode + verify a JWT, trying current + previous secret.

    Used during the rollover window (24h recommended). Tokens signed
    with either secret verify successfully; new tokens use the
    current secret. After the window, set JWT_SECRET_PREVIOUS=""
    to drop the fallback.
    """
    for secret in (settings.jwt_secret, settings.jwt_secret_previous):
        if not secret:
            continue
        try:
            return jwt.decode(token, secret, algorithms=[settings.jwt_alg],
                              options={"require": ["exp", "iat", "sub"]})
        except jwt.InvalidSignatureError:
            continue
    raise jwt.InvalidTokenError("token not signed by current or previous secret")
```

**Good example (Next.js headers):**

```javascript
// web/next.config.mjs
const securityHeaders = [
  { key: 'Content-Security-Policy', value: "default-src 'self'; ..." },
  { key: 'Strict-Transport-Security', value: 'max-age=63072000; includeSubDomains; preload' },
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'X-Frame-Options', value: 'DENY' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
];
const nextConfig = {
  reactStrictMode: true,
  async headers() { return [{ source: '/(.*)', headers: securityHeaders }]; },
};
```

---

## Testing Strategy

- **Rate limiter unit tests (8)**: window expires, multiple keys
  independent, action-policies enforced, exception isolation
- **Auth router integration (2)**: 6th login attempt returns 429,
  audit row written on rate-limit-exceeded
- **Secret rotation (4)**: decode_token_rotating accepts current +
  previous, rejects unrelated secret, missing-previous falls back
  to current, malformed token raises
- **Front-end headers (3)**: rendered page includes CSP, HSTS,
  X-Frame-Options (asserted via Next.js's built-in `headers()`
  helper in a test route)
- **Regression**: full 343-test suite stays green
- **Coverage**: ≥ 90% (preserves the ≥ 80% gate)

---

## Boundaries

**Always do:**
- Run `pytest -p no:randomly` before committing
- New tests fail first (RED), then minimal code (GREEN), then
  refactor
- Rate-limit failures MUST emit audit events with the
  `auth.rate_limited` / `team.invite_rate_limited` actions
- Rate-limit configuration goes through `Settings` (env-driven)
- Front-end headers are restrictive by default; widening is a
  separate change with a spec

**Ask first:**
- Adding a new dep (e.g., `slowapi`, `redis-py`)
- Changing `Settings` field types or names
- Touching `migrations/001_init.sql` (cycle 1, frozen)

**Never do:**
- Block the primary request when the rate-limiter raises (the
  limiter MUST fail-open if its internal state is corrupt)
- Hardcode rate-limit thresholds in the router (always go through
  Settings)
- Allow `unsafe-inline` in CSP without a documented justification
  (Next.js requires it for inline styles today — that's the only
  exception, and it's called out in the config comment)
- Set `JWT_SECRET_PREVIOUS` to a string longer than 4096 bytes
  (defensive guard against accidental copy-paste of an API key)

---

## Acceptance Criteria

### Rate limiting

- [ ] **AC-RL-01** — `POST /api/auth/login` allows 5 attempts / 15 min
      per IP; the 6th returns `429 Too Many Requests` with a
      `Retry-After` header.
- [ ] **AC-RL-02** — `POST /api/auth/signup` allows 5 / hour per IP
      (anti-enumeration). 6th in window returns 429.
- [ ] **AC-RL-03** — `POST /api/teams/{id}/invitations` allows
      20 / hour per owner (spam defense). 21st returns 429.
- [ ] **AC-RL-04** — Each 429 response writes one row to
      `security_events` with `action='auth.rate_limited'` (or
      `team.invite_rate_limited`), `actor_id=null` (anonymous),
      `metadata={'ip': ..., 'limit': ...}`.
- [ ] **AC-RL-05** — `RateLimiter` Protocol + `InMemoryRateLimiter`
      shipped. Sliding window. Thread-safe (RLock).
- [ ] **AC-RL-06** — `RedisRateLimiter` stub class exists (cycle-7
      TODO: real implementation); passes `isinstance(r, RateLimiter)`.

### Secret rotation

- [ ] **AC-SR-01** — `decode_token_rotating(token, settings)` accepts
      tokens signed with `settings.jwt_secret` OR
      `settings.jwt_secret_previous`.
- [ ] **AC-SR-02** — Tokens signed with neither raise
      `jwt.InvalidTokenError`.
- [ ] **AC-SR-03** — `Settings.jwt_secret_previous: str = ""` defaults
      to empty (no-op when no rotation in progress).
- [ ] **AC-SR-04** — `auth_service.decode_token()` calls
      `decode_token_rotating()` so existing endpoints get rotation
      for free.
- [ ] **AC-SR-05** — `validate_security()` from cycle 5 enforces:
      if `jwt_secret_previous` is set, it must be ≥ 32 bytes
      (defensive: catches accidental short-string bug).
- [ ] **AC-SR-06** — `docs/security.md` documents the 4-step
      rotation playbook (see "Docs" below).

### Front-end headers

- [ ] **AC-WEB-01** — `GET /` response includes
      `Content-Security-Policy` (default-src 'self', script-src
      'self' 'unsafe-inline' for Next.js bootstrap).
- [ ] **AC-WEB-02** — Response includes
      `Strict-Transport-Security: max-age=63072000;
      includeSubDomains; preload`.
- [ ] **AC-WEB-03** — Response includes `X-Content-Type-Options:
      nosniff`, `X-Frame-Options: DENY`,
      `Referrer-Policy: strict-origin-when-cross-origin`.
- [ ] **AC-WEB-04** — Headers apply to all routes
      (`source: '/(.*)'` matcher).
- [ ] **AC-WEB-05** — 3 vitest tests assert the headers are
      present on the rendered page.

### Docs (T-505 from cycle 5, folded into T-606)

- [ ] **AC-DOC-01** — `docs/security.md` covers:
      - secret rotation playbook (4 steps: generate new,
        deploy with both, monitor for old-secret failures,
        drop previous after 24h)
      - audit review query cookbook (top 10 ops queries:
        failed logins by IP, unusual signup velocity,
        rate-limit spikes, permission denials, etc.)
      - incident response checklist (when audit-log alert
        fires, what's the triage ladder)
      - .env reference for every prod-required secret

### Regression

- [ ] **AC-REG-01** — All 343 existing tests still pass.
- [ ] **AC-REG-02** — `pytest -p no:randomly` reports ≥ 365 tests,
      ≥ 90% coverage.
- [ ] **AC-REG-03** — `ruff check` + `ruff format --check` + `mypy
      app/` all clean.
- [ ] **AC-REG-04** — `npm run typecheck` + `npm test` clean.

---

## Out of Scope

- **MFA / 2FA / WebAuthn** — cycle 7+ (requires user-profile
  schema + UI changes; explicitly out of cycle 6's scope)
- **Distributed rate limiting (Redis adapter real impl)** —
  cycle 7 (Redis is a new dep; cycle 6 ships the Protocol +
  stub + InMemory implementation)
- **OAuth provider integration** — out of scope
- **Coupons / annual billing** — feature work, not security;
  cycle 8+
- **GDPR data export / right-to-delete** — cycle 8
- **Penetration testing** — separate engagement

---

## Open Questions

1. **Q: Should rate-limit thresholds be configurable per-team, or
   globally?** Recommend: **globally** for v1, per-team in cycle 7
   when the team-management UI is mature enough to expose it.
   Per-team config also requires a migration + RLS update.

2. **Q: Should the `JWT_SECRET_PREVIOUS` rollover window be
   configurable, or hard-coded at 24h?** Recommend: **24h is a
   convention, not enforced in code**. Operators can leave
   `JWT_SECRET_PREVIOUS` set longer if needed; the cost is just
   that old tokens keep verifying.

3. **Q: Should CSP allow `'unsafe-eval'` for Next.js dev mode
   (HMR)?** Recommend: **yes in dev, no in prod**. We can
   detect `NODE_ENV !== 'production'` in the Next config.

4. **Q: Should rate-limit-exceeded events trigger an admin
   notification (email/Slack)?** Recommend: **deferred to cycle 7**.
   The audit row is enough for v1; an alert-routing layer is its
   own scope.

5. **Q: Does cycle-6's spec cover docs/security.md (T-505 from
   cycle 5)?** Recommend: **yes, fold it into T-606**. Cycle 5's
   T-505 was just docs + final verify; cycle 6 needs the same
   docs anyway. Saves a commit.