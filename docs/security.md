# Security Runbook

> **Audience:** ops engineers + on-call responders.
> **Last reviewed:** 2026-07-04 (cycle 6 T-606).
> **Source cycle:** cycle 5 (validators + audit log + RLS) + cycle 6
> (rate limiting + secret rotation + front-end headers).

This doc covers:

1. **Secret rotation playbook** — zero-downtime `JWT_SECRET`
   rotation (T-604).
2. **Audit review query cookbook** — top 10 ops queries against
   `security_events` (cycle 5 T-502/T-503).
3. **Incident response checklist** — when an alert fires, what
   to do.
4. **`.env` reference** — every prod-required secret annotated
   with its validator.
5. **Front-end security headers** — what each header does and
   why we set it (cycle 6 T-605).

---

## 1. Secret rotation playbook

### JWT_SECRET

The most common rotation. Operators rotate the JWT signing key
on a regular schedule (PCI-DSS / SOC2 controls typically demand
this). Cycle 6 T-604 ships a dual-verify window so the rollover
is zero-downtime.

**The 4 steps:**

```bash
# 1. Generate the new secret
NEW_SECRET=$(openssl rand -base64 48)
echo "$NEW_SECRET"   # write this down — you'll need it for step 2

# 2. Deploy with BOTH secrets for the rollover window
#    (Railway: set env vars; Vercel: project settings; etc.)
#    JWT_SECRET=<NEW>
#    JWT_SECRET_PREVIOUS=<OLD>      # the secret currently in use
#
#    During this window:
#      - tokens issued with <NEW>     verify with JWT_SECRET
#      - tokens issued with <OLD>     verify with JWT_SECRET_PREVIOUS
#      - new tokens are signed with JWT_SECRET

# 3. Monitor for "wrong secret" failures (24h, convention = jwt_ttl_seconds)
#    These look like auth.login.failure events with success=false.
#    A spike means tokens are being signed with a secret that's
#    NOT in {current, previous} — i.e. somewhere in the system
#    hasn't picked up the rotation.
psql -c "
    SELECT count(*), date_trunc('hour', created_at) AS hour
    FROM security_events
    WHERE action = 'auth.login.failure'
      AND created_at > now() - interval '24 hours'
    GROUP BY hour
    ORDER BY hour DESC;
"

# 4. After the rollover window closes (default 24h, matching jwt_ttl_seconds),
#    drop JWT_SECRET_PREVIOUS. Old tokens now fail; no one should
#    still hold them since their lifetime is <24h.
#    JWT_SECRET=<NEW>
#    JWT_SECRET_PREVIOUS=           # empty
```

**Why dual-verify:** without `JWT_SECRET_PREVIOUS`, every
existing token fails the moment the new secret deploys. Every
active user gets logged out within 24h of the rotation.
With dual-verify, the rollover is invisible to users.

**Why a validator enforces ≥32 bytes on `JWT_SECRET_PREVIOUS`:**
catches the "I accidentally copy-pasted a short stub" bug before
it ships. The dev default is empty so this doesn't trip pytest.

### Other secrets

- **`STRIPE_API_KEY`** — rotate from the Stripe dashboard.
  No dual-verify needed: Stripe's webhook signature verification
  uses the same key for both sides, so a clean cutover is fine.
  The cycle-5 validator rejects the placeholder value when
  `USE_MOCKS=false` in production.
- **`LINE_CHANNEL_SECRET`** — rotate from the LINE Official
  Account Manager. Webhook signatures will fail for ~5 minutes
  while LINE propagates the new secret; expect a brief spike in
  webhook-rejection log entries.
- **`SUPABASE_SERVICE_ROLE_KEY`** — rotate from the Supabase
  dashboard. Server-side queries will fail until the new key
  propagates; treat as a deploy-window thing.

---

## 2. Audit review query cookbook

The `security_events` table (cycle 5 T-502) is append-only at the
DB level (no UPDATE/DELETE RLS policies). Every login, signup,
invitation accept, rate-limit-exceeded event, and webhook
verification failure lands here with the actor's IP + User-Agent.

**Schema:**

```
id            UUID
actor_id      UUID (nullable for anonymous actions)
action        TEXT (auth.signup, auth.login, auth.login.failure,
              auth.rate_limited, team.accept_invite,
              team.invite_rate_limited, billing.checkout, ...)
target_id     UUID (nullable)
ip            TEXT (X-Forwarded-For first hop)
user_agent    TEXT
success       BOOLEAN
metadata      JSONB
created_at    TIMESTAMPTZ
```

**Top 10 ops queries:**

```sql
-- 1. Failed logins by IP, last 24h
--    (alert when a single IP has > 20 failures)
SELECT ip, count(*) AS failures
FROM security_events
WHERE action = 'auth.login.failure'
  AND created_at > now() - interval '24 hours'
GROUP BY ip
HAVING count(*) > 20
ORDER BY failures DESC;

-- 2. Signup velocity per IP (anti-sybil detection)
--    (alert when a single IP has > 5 signups in 1h)
SELECT ip, count(*) AS signups, min(created_at) AS first, max(created_at) AS last
FROM security_events
WHERE action = 'auth.signup'
  AND created_at > now() - interval '1 hour'
GROUP BY ip
HAVING count(*) > 5
ORDER BY signups DESC;

-- 3. Rate-limit spikes (today)
--    (alert when total rate-limit hits > 100/day)
SELECT count(*), metadata->>'action' AS action
FROM security_events
WHERE action IN ('auth.rate_limited', 'team.invite_rate_limited')
  AND created_at > current_date
GROUP BY metadata->>'action'
ORDER BY count(*) DESC;

-- 4. Accepted invitations, last 7d (org growth signal)
SELECT date_trunc('day', created_at) AS day, count(*)
FROM security_events
WHERE action = 'team.accept_invite' AND success = true
  AND created_at > now() - interval '7 days'
GROUP BY day
ORDER BY day;

-- 5. Top actors by failed-login ratio (1+ failed vs 10+ successful)
--    (alert when ratio > 0.5 — account may be compromised)
SELECT actor_id,
       sum(CASE WHEN success THEN 1 ELSE 0 END) AS successes,
       sum(CASE WHEN success THEN 0 ELSE 1 END) AS failures
FROM security_events
WHERE action IN ('auth.login', 'auth.login.failure')
  AND created_at > now() - interval '24 hours'
GROUP BY actor_id
HAVING sum(CASE WHEN success THEN 0 ELSE 1 END) > 0
ORDER BY failures DESC
LIMIT 20;

-- 6. JWT decode failures from a wrong secret (rotation signal)
--    (alert when count > 5 in 5min — something's misconfigured)
SELECT count(*), date_trunc('minute', created_at) AS minute
FROM security_events
WHERE metadata->>'action' = 'auth.login.failure'
  AND created_at > now() - interval '5 minutes'
GROUP BY minute
ORDER BY minute DESC;

-- 7. Active users (unique actors with any event in last 24h)
SELECT count(DISTINCT actor_id)
FROM security_events
WHERE created_at > now() - interval '24 hours'
  AND actor_id IS NOT NULL;

-- 8. Anonymous actions (failed logins, rate limits) — privacy-aware
--    (no PII; just ops signal)
SELECT action, count(*)
FROM security_events
WHERE actor_id IS NULL
  AND created_at > now() - interval '24 hours'
GROUP BY action
ORDER BY count(*) DESC;

-- 9. Per-team invitation acceptance rate (last 30d)
SELECT
    target_id AS team_id,
    count(*) FILTER (WHERE action = 'team.invite_rate_limited') AS rate_limited,
    count(*) FILTER (WHERE action = 'team.accept_invite' AND success) AS accepted
FROM security_events
WHERE created_at > now() - interval '30 days'
GROUP BY target_id
ORDER BY accepted DESC;

-- 10. Top user-agents by failure count (bot vs. real-browser signal)
SELECT user_agent, count(*)
FROM security_events
WHERE success = false
  AND created_at > now() - interval '24 hours'
GROUP BY user_agent
ORDER BY count(*) DESC
LIMIT 10;
```

**Mock-mode equivalent:** in dev, the same queries work against
`var/`-backed tables; the cycle-5 mock schema mirrors the real
Supabase schema so SQL is portable.

---

## 3. Incident response checklist

When an alert fires (from a query above, a SIEM rule, or a
customer report):

### Triage (0-15 min)

- [ ] **Check the alert's scope** — single user, single IP,
      single team, or global? Determines response urgency.
- [ ] **Look at `security_events` for the actor/IP** —
      `SELECT * FROM security_events WHERE actor_id = '<id>'
      ORDER BY created_at DESC LIMIT 50;` (or by IP).
- [ ] **Classify:** brute-force? compromised account? misconfig?
      bot traffic? Each has a different playbook.

### Containment (15-60 min)

- [ ] **Brute-force on a single IP** — the rate limiter already
      blocks after 5 attempts. Confirm the limit is firing
      (`auth.rate_limited` rows in `security_events`). If the
      IP is rotating (botnet), consider adding a CIDR block at
      the load balancer.
- [ ] **Compromised account** — invalidate the user's active
      sessions by rotating `JWT_SECRET` (Section 1). Force
      password reset. Add a `cycle-7 TODO` for an admin
      "revoke all sessions" endpoint.
- [ ] **Webhook secret leak** — rotate `STRIPE_WEBHOOK_SECRET`
      / `LINE_CHANNEL_SECRET` from the upstream provider's
      dashboard. The old secret stops verifying immediately.

### Recovery (1-24h)

- [ ] **Audit** — capture the relevant `security_events` rows
      for post-mortem.
- [ ] **Notify** — if customer data was exposed, follow the
      breach-notification runbook (out of scope here; see legal).
- [ ] **Patch** — if the root cause was a code bug, file a
      follow-up cycle.

### Post-mortem (within 7d)

- [ ] **Write up** — what fired, what was missed, what
      detectors need improving.
- [ ] **Add to this runbook** — anything we did that the next
      responder needs to know.
- [ ] **Cycle plan** — feed follow-up work into the next
      AIDLC cycle.

---

## 4. `.env` reference

Every env var the backend reads, with its validator (cycle 5
T-501 + cycle 6 T-604) and prod requirement:

| Var | Default | Dev/Test override | Prod requirement | Validator |
|-----|---------|--------------------|------------------|-----------|
| `ENV` | `dev` | `dev` / `test` / `dev-*` / `test-*` exempt | `production` / `staging` / `preview` recommended | (always runs) |
| `JWT_SECRET` | `dev-jwt-secret-change-me` | accepted in dev/test | not the default, ≥ 32 bytes | `validate_jwt_secret` |
| `JWT_SECRET_PREVIOUS` | empty | accepted in dev/test | empty OR ≥ 32 bytes | `validate_jwt_secret_previous` |
| `JWT_TTL_SECONDS` | 86400 (24h) | accepted | set to your retention policy | (none) |
| `JWT_ALG` | `HS256` | accepted | typically HS256; only change with a security review | (none) |
| `CORS_ORIGINS` | `["*"]` | accepted in dev/test | explicit list of allowed origins | `validate_cors_origins` |
| `LINE_CHANNEL_SECRET` | `dev-line-channel-secret-change-me` | accepted in dev/test | not the default | `validate_line_channel_secret` |
| `STRIPE_API_KEY` | empty | accepted when `USE_MOCKS=true` | a real `sk_live_...` or `sk_test_...` key (when `USE_MOCKS=false`) | `validate_stripe_api_key` |
| `STRIPE_WEBHOOK_SECRET` | empty | accepted | set when real Stripe enabled | (none — placeholder allowed) |
| `STRIPE_PRICE_GROWTH` | empty | accepted | set when real Stripe enabled | (none) |
| `STRIPE_PRICE_TEAM` | empty | accepted | set when real Stripe enabled | (none) |
| `USE_MOCKS` | `true` | accepted | `false` in prod (real services) | (none — flag, not secret) |
| `USE_REAL_SUPABASE` | `false` | accepted | `true` in prod (if Supabase) | (none — flag) |
| `USE_REAL_LINE` | `false` | accepted | `true` in prod | (none — flag) |
| `USE_REAL_AI` | `false` | accepted | `true` in prod | (none — flag) |
| `SUPABASE_URL` | empty | accepted | set when `USE_REAL_SUPABASE=true` | (none) |
| `SUPABASE_ANON_KEY` | empty | accepted | set when `USE_REAL_SUPABASE=true` | (none) |
| `SUPABASE_SERVICE_ROLE_KEY` | empty | accepted | set when `USE_REAL_SUPABASE=true` | (none) |
| `LINE_CHANNEL_ACCESS_TOKEN` | empty | accepted | set when `USE_REAL_LINE=true` | (none) |
| `ANTHROPIC_API_KEY` | empty | accepted | set when `USE_REAL_AI=true` | (none) |
| `GEMINI_API_KEY` | empty | accepted | set when `USE_REAL_AI=true` (Gemini provider) | (none) |
| `FRONTEND_URL` | `http://localhost:3000` | accepted | your real frontend URL | (none) |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | accepted | your real API URL | (none) |

**Secret-generation cheatsheet:**

```bash
# JWT_SECRET (and JWT_SECRET_PREVIOUS during rotation)
python -c 'import secrets; print(secrets.token_urlsafe(64))'

# LINE_CHANNEL_SECRET — 32+ bytes from the LINE console
# (you can't generate this; it's issued by LINE)

# STRIPE_API_KEY — issued by Stripe dashboard
# Test mode: sk_test_...    Live mode: sk_live_...
```

---

## 5. Front-end security headers

Cycle 6 T-605 ships these on every route via `next.config.mjs`:

| Header | Value | Why |
|--------|-------|-----|
| `Content-Security-Policy` | `default-src 'self'; script-src 'self' 'unsafe-inline'; frame-src https://js.stripe.com; ...` | XSS defense — restricts what the browser is allowed to load. `'unsafe-inline'` for scripts is the only unsafe directive (Next.js's bootstrap is inline). Tighten to nonce-based CSP in cycle 7+ if a violation-reporting channel is added. |
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains; preload` | Forces HTTPS for 2 years. The `preload` directive commits us to maintaining HTTPS forever; remove it until you're sure you can keep that promise. |
| `X-Content-Type-Options` | `nosniff` | Stops the browser from guessing content types; defense against MIME-sniffing attacks. |
| `X-Frame-Options` | `DENY` | Prevents the dashboard from being embedded in an iframe (clickjacking defense). |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | The Referer header only contains the origin (not full URL) on cross-origin requests. |
| `Permissions-Policy` | `geolocation=(), microphone=(), camera=(), payment=(self "https://js.stripe.com")` | Disables unused browser APIs. `payment=` explicitly allows Stripe Checkout. |

**Testing the headers locally:**

```bash
curl -I http://localhost:3000/
# Expect: HTTP/1.1 200 OK
#         Content-Security-Policy: default-src 'self'; ...
#         Strict-Transport-Security: max-age=63072000; ...
#         X-Content-Type-Options: nosniff
#         X-Frame-Options: DENY
#         Referrer-Policy: strict-origin-when-cross-origin
#         Permissions-Policy: ...
```

**Why `'unsafe-inline'` for scripts:** Next.js's bootstrap
script is inline today. The alternative (nonce-based CSP) requires
modifying Next.js's render pipeline to inject a unique nonce per
page; that's a cycle-7+ effort. The current setting still defends
against XSS in `<script src="...">` and `<iframe src="...">` —
the common attack vectors.

**CSP-violation reporting:** not currently enabled. If you
want it, add `report-uri /api/csp-report` (and a corresponding
endpoint) — the violation reports land in your logs as `security_events`
rows with `action='csp.violation'`. Cycle-7 work.

---

## Cross-references

- `docs/billing.md` — Stripe-specific rotation + plan changes
- `docs/production-deploy.md` — Railway deploy guide (env var setup)
- `docs/runbook.md` — generic deploy + ops runbook
- `migrations/004_security_events.sql` — `security_events` schema + RLS
- `migrations/005_rls_gaps.sql` — write-path RLS policies
- `app/security_validation.py` — the validators
- `app/secret_rotation.py` — `decode_token_rotating()`
- `app/rate_limit.py` — the rate limiter
- `app/audit_log.py` — the audit-log helpers
- `web/next.config.mjs` — the front-end headers
- `backend/tests/test_security_validation.py` — validator tests
- `backend/tests/test_audit_log.py` — audit-log tests (incl. rate-limit hooks)
- `backend/tests/test_rate_limit.py` — rate-limiter tests
- `backend/tests/test_secret_rotation.py` — rotation tests
- `web/__tests__/headers.test.ts` — front-end header tests
---

## 6. Cycle 7 addendum

Cycle 7 ships three operational-security features layered on top
of the cycle-5/6 foundations. This section covers the new ops
surface.

### 6.1 Redis-backed rate limiter (multi-pod)

Cycle 6's `InMemoryRateLimiter` only works in single-process
deploys. A 2-pod Railway / Fly / Render deploy means an attacker
brute-forcing against pod A gets 5 attempts per IP; if they
rotate to pod B they get 5 more. Cycle 7 ships `RedisRateLimiter`
with sliding-window state in Redis (sorted sets + ZADD +
ZREMRANGEBYSCORE + ZCARD + EXPIRE) so the limit is consistent
cluster-wide.

**Provisioning:**

1. Provision a Redis instance (Upstash, Redis Cloud, Render Key-Value,
   or self-hosted). Note the `REDIS_URL` (e.g.,
   `redis://default:<password>@<host>.upstash.io:6379`).
2. Set `RATE_LIMIT_BACKEND=redis` and `REDIS_URL=...` in your
   prod env. The factory lazily imports `redis-py`; dev / laptop
   setups without Redis still work (defaults to `memory`).
3. Verify the keyspace: the limiter writes keys with prefix `rl:`
   (e.g., `rl:auth.login:1.2.3.4`). TTL is `window_seconds + 60s`.

**Monitoring:**

```bash
# Check the keyspace size (number of rate-limit buckets)
redis-cli -u $REDIS_URL KEYS 'rl:*' | wc -l

# Watch a single IP's bucket fill up
redis-cli -u $REDIS_URL ZCARD 'rl:auth.login:1.2.3.4'

# Top 10 most-active keys
redis-cli -u $REDIS_URL --scan --pattern 'rl:*' | xargs -I{} sh -c 'echo "$(redis-cli -u $REDIS_URL ZCARD {}) {}"' | sort -rn | head
```

**What to do when Redis is down:**

The `RedisRateLimiter` fail-open contract returns `allowed=True`
on any Redis exception (ConnectionError, TimeoutError, auth
failure, OOM). The application keeps serving traffic, but
`logger.error("rate_limit redis unavailable ...")` fires on every
rate-limit check. Two things to check:

1. **Are users actually being rate-limited?** If `audit_log`
   shows zero `action='auth.rate_limited'` rows during an outage,
   the fail-open is working as designed.
2. **Did the audit row for the (now-missed) rate-limit trip get
   written?** No — the audit row is written *after* the rate-limit
   check fails, and the rate-limit check failed-open. So the
   audit trail is incomplete for the duration of the outage.

Recovery: the rate-limit state is **not** persisted across Redis
restarts (the sorted set buckets expire on TTL anyway). When
Redis comes back, every IP gets a fresh quota. Brute-force
attackers will likely retreat during the outage window because
they're making no progress, but watch the audit log for a spike
in successful logins (post-outage they may come back).

### 6.2 Per-team rate-limit thresholds

Team admins can override the system-default rate-limit policies
via `PATCH /api/teams/{id}/rate_limits`. The endpoint is
owner-only; any team member can `GET` the current effective
limits (override OR default).

**Admin guide:**

```bash
# Get current effective limits (returns override or default)
curl https://app.example.com/api/teams/$TEAM_ID/rate_limits \
  -H "Authorization: Bearer $OWNER_TOK"
# → {"login_per_15min": 5, "signup_per_hour": 5, "invite_per_hour": 20}

# Stricten: enterprise team with stricter login policy
curl -X PATCH https://app.example.com/api/teams/$TEAM_ID/rate_limits \
  -H "Authorization: Bearer $OWNER_TOK" \
  -H "Content-Type: application/json" \
  -d '{"login_per_15min": 3, "invite_per_hour": 5}'

# Loosen: marketing team with more invites
curl -X PATCH https://app.example.com/api/teams/$TEAM_ID/rate_limits \
  -H "Authorization: Bearer $OWNER_TOK" \
  -H "Content-Type: application/json" \
  -d '{"invite_per_hour": 50}'

# Reset to defaults: clear the override row (DELETE endpoint
# coming in cycle 8; for now, set to system defaults via PATCH)
```

**What the limits mean:**

- **`login_per_15min`**: failed + successful login attempts
  counted together. So 5 wrong passwords = 5/5 quota; the 6th
  attempt (right or wrong) returns 429.
- **`signup_per_hour`**: signup attempts per IP, not per team.
  Defense against scripted account-creation / enumeration
  probing.
- **`invite_per_hour`**: invitation creations per owner (not per
  IP — the owner is authenticated and may be on a moving IP).
  Defense against spam.

**Override rules:**

- Each value must be `≥ 1` (enforced by both the API Pydantic
  validator and the DB `CHECK` constraint). The API returns
  `422 Unprocessable Entity` for 0 or negative values.
- Empty `PATCH` payloads return `422` ("at least one of
  login_per_15min, signup_per_hour, invite_per_hour must be
  provided").
- Per-team overrides apply to team-scoped endpoints (e.g.,
  invitation creation). The `/api/auth/login` and
  `/api/auth/signup` endpoints continue to use the system-wide
  defaults because we don't know which team the user belongs to
  until after they authenticate.
- Overrides take effect immediately on the next request (the
  cached `InMemoryRateLimiter` is invalidated on PATCH).

**Rollback to defaults:**

Cycle 7 doesn't have a `DELETE /api/teams/{id}/rate_limits`
endpoint yet. To roll back:

1. Query the current override row.
2. PATCH with all three values set to system defaults (5 / 5 / 20)
   OR set values to known-good limits.
3. (Cycle 8) Direct DB delete via the admin SDK.

**Auditing:**

Every PATCH writes no audit row (cycle 7 doesn't have a
`team.rate_limits.changed` action yet — cycle-8 polish). For
now, rely on git history + change log to track who changed what
when.

### 6.3 CSP violation reporting

Cycle 6's CSP used `'unsafe-inline'` for scripts because
Next.js's bootstrap is inline. That's the one compromise. Cycle
7's CSP violation reporting is the missing half: when the
browser blocks a script per the CSP, it can POST a violation
report to `/api/csp-report` and we log it to `security_events`.

**What a CSP violation looks like in `security_events`:**

```json
{
  "id": "...",
  "actor_id": null,
  "action": "csp.violation",
  "target_id": null,
  "ip": "203.0.113.42",
  "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
  "success": true,
  "metadata": {
    "violated_directive": "script-src 'self'",
    "blocked_uri": "https://evil.example.com/x.js",
    "document_uri": "https://app.example.com/dashboard"
  },
  "created_at": "2026-07-04T..."
}
```

**Interpretation:**

- **`action='csp.violation'`** + `success=true` — the report was
  accepted (the endpoint always returns 204, even for malformed
  bodies, so "success" here means "received", not "report was
  valid").
- **`metadata.violated_directive`** — what the browser was
  trying to do. `"script-src 'self'"` = browser tried to load a
  script from a non-self origin. `"style-src 'unsafe-inline'"` =
  browser blocked an inline style. `"connect-src 'self'"` = browser
  blocked an XHR/fetch to a non-self origin.
- **`metadata.blocked_uri`** — what was blocked. This is the
  smoking gun for XSS attempts: a real attacker's payload URL
  shows up here.
- **`metadata.document_uri`** — the page the user was on when
  the violation happened. Useful for narrowing down a compromised
  page or a specific embed.

**When to investigate:**

- **New `violated_directive` you've never seen before** —
  something in your app changed and the CSP didn't catch up.
  Check the commit log.
- **`blocked_uri` from a non-trusted origin** — likely a
  successful XSS probe. The browser is doing its job; you should
  be alerted.
- **Spike in CSP violations from a single IP** — could indicate
  a misbehaving client (e.g., a buggy extension) or a script-kiddie
  scanning your site.
- **CSP violations on your own origins** — usually a misconfigured
  `<script>` tag or inline style. Fix the source.

**Ops dashboard query cookbook** (10-cycle-5 + 4-cycle-7):

```sql
-- New CSP violation type appeared in the last 24h
-- (alert: new violation type = potential XSS probe or app change)
SELECT metadata->>'violated_directive' AS directive,
       count(*) AS hits
FROM security_events
WHERE action = 'csp.violation'
  AND created_at > now() - interval '24 hours'
GROUP BY directive
ORDER BY hits DESC;

-- Top blocked URIs (alert on untrusted origins)
SELECT metadata->>'blocked_uri' AS blocked_uri,
       count(*) AS hits
FROM security_events
WHERE action = 'csp.violation'
  AND created_at > now() - interval '24 hours'
  AND metadata->>'blocked_uri' NOT LIKE '%your-domain.com%'
GROUP BY blocked_uri
ORDER BY hits DESC
LIMIT 20;

-- CSP violations per page (find a buggy page)
SELECT metadata->>'document_uri' AS page,
       count(*) AS hits
FROM security_events
WHERE action = 'csp.violation'
  AND created_at > now() - interval '7 days'
GROUP BY page
ORDER BY hits DESC
LIMIT 20;
```

**Cycle-8 note:** when we go nonce-based CSP (replacing the
`'unsafe-inline'` compromise), the violation data we're
collecting in cycle 7 is exactly the data we need to validate
that the nonce migration is safe. The `report-uri` directive
will be replaced with a per-violation nonce report, but the
backend endpoint stays the same.

---

## 7. Cross-references (cycle 7)

- `app/redis_rate_limiter.py` — `RedisRateLimiter` real impl
- `app/rate_limit_factory.py` — env-driven `RATE_LIMIT_BACKEND`
  selection
- `app/routers/teams.py` — per-team rate-limit GET + PATCH +
  per-team invite cap enforcement (`_get_or_build_team_limiter`)
- `app/services/team_service.py` — `get_effective_rate_limits` +
  `set_team_rate_limits`
- `migrations/006_team_rate_limits.sql` — `team_rate_limits`
  table + RLS
- `app/routers/csp_report.py` — `POST /api/csp-report` endpoint
- `web/lib/csp_report.ts` — client-side `reportCspViolation()`
  helper
- `backend/tests/test_redis_rate_limit.py` — Redis limiter tests
- `backend/tests/test_team_rate_limits.py` — per-team tests
- `backend/tests/test_csp_report.py` — CSP-report endpoint tests
- `web/__tests__/csp_report.test.ts` — client-side helper tests
