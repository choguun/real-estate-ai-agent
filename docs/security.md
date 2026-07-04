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