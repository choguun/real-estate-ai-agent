# Spec: Cycle 5 — Security Hardening (JWT/CORS defaults, RLS gaps, audit log)

> **Status:** specifying
> **Branch:** `feat/security-hardening`
> **Cycle origin:** Deferred from cycle 4 (review-critical C3) + audit log as cycle-5 work.

---

## Objective

Cycle 4 shipped with three **silent footguns** that the post-cycle review
flagged as P0 / C3:

1. `JWT_SECRET=dev-jwt-secret-change-me` is accepted at startup, so a
   misconfigured prod deploy signs every user with a public secret.
2. `CORS_ORIGINS=["*"]` is the default, so any browser anywhere can call
   authenticated endpoints in production.
3. `LINE_CHANNEL_SECRET=dev-line-channel-secret-change-me` is the same trap
   (cycle-1 inherited it).

This cycle **fail-fasts on insecure defaults in non-dev environments**,
adds an **audit log** for sensitive events, and **closes the gaps** the
review also surfaced in the RLS policies (write paths, membership changes,
billing-event deletes).

**Who the user is:** the same operator from cycles 1-4 (small Thai real
estate agency). They deploy via Railway; one missed env var should not
silently expose their users to token forgery.

**Success = at app startup:**
1. `ENV=production` with `JWT_SECRET=dev-jwt-secret-change-me` → exits
   non-zero with `JWT_SECRET is set to the default; refusing to start`.
2. `ENV=production` with `JWT_SECRET=tooshort` → exits non-zero with
   `JWT_SECRET must be ≥32 bytes (got 8)`.
3. `ENV=production` with `CORS_ORIGINS=["*"]` → exits non-zero with
   `CORS_ORIGINS cannot be ["*"] in production; set explicit origins`.
4. `ENV=production` with `LINE_CHANNEL_SECRET=dev-...-change-me` → exits
   non-zero with the same shape.
5. Login, signup, and accept-invitation write an audit row to
   `security_events` with `{actor, action, target, ip, ua, success}`.
6. RLS test gap: real Supabase write policies for `team_invitations`,
   `team_memberships`, `billing_customers` cover the role-permitted paths
   that the cycle-3/4 routers exercise.

**Out of scope (explicit):** Adding MFA, rate-limiting, secret rotation
tooling (cycle 6), SOC2 controls, OAuth provider integration.

---

## Commands

```bash
# Validate env on startup (new)
ENV=production JWT_SECRET=dev-jwt-secret-change-me uvicorn app.main:app
# → exits 2 with JWT_SECRET failure message

# Run the new audit-log + RLS tests
cd backend
pytest tests/test_security_validation.py tests/test_audit_log.py tests/test_rls_smoke.py -v

# Run the full suite (regression)
pytest -p no:randomly  # 302 → 320+ tests

# Lint / format / types
ruff check app tests
ruff format --check app tests
mypy app
```

---

## Project Structure

```
backend/app/
  config.py                 # NEW: Settings._validate_post_load() fail-fast
  security_validation.py    # NEW: pure validators (testable in isolation)
  audit_log.py              # NEW: write_event() + AuditEvent model
  main.py                   # MOD: call Settings.validate() at startup
  services/auth.py          # MOD: emit audit on login/signup/liff_login
  routers/teams.py          # MOD: emit audit on accept_invitation
  routers/billing.py        # MOD: emit audit on checkout/portal calls
  migrations/004_security_events.sql  # NEW: security_events table + RLS
  tests/
    test_security_validation.py       # NEW: 12 tests
    test_audit_log.py                 # NEW: 6 tests
    test_rls_smoke.py                 # EXTEND: 4 more policy tests

docs/
  security.md               # NEW: secret-rotation runbook + audit review
```

---

## Code Style

Cycle-5 follows the cycle-3/4 pattern: pure validators + thin glue.

**Good example (validator pattern):**

```python
# app/security_validation.py
def validate_jwt_secret(value: str, env: str) -> None:
    """Raise ValueError if the JWT secret is unsafe for `env`."""
    if env in ("dev", "test") and value.startswith("dev-"):
        return  # dev: explicit "dev-" prefix means "I know this is fake"
    if value == "" or value == "dev-jwt-secret-change-me":
        raise ValueError(
            f"JWT_SECRET is set to the default value; refusing to start "
            f"(env={env}). Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(64))'"
        )
    if len(value.encode("utf-8")) < 32:
        raise ValueError(
            f"JWT_SECRET must be ≥32 bytes (got {len(value)}); use a random 64+ byte secret."
        )
```

**Bad example (caught by review):**

```python
# DON'T DO THIS — silently accepts default
class Settings(BaseSettings):
    jwt_secret: str = "dev-jwt-secret-change-me"   # ← ships to prod
```

```python
# DON'T DO THIS — wildcard CORS + credentials = CSRF
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # ← browsers reject this with credentials
    allow_credentials=True,
)
```

**Audit-event pattern:**

```python
# app/audit_log.py
@dataclass(frozen=True)
class AuditEvent:
    actor_id: str | None       # user_id (None for anonymous)
    action: str                # "auth.login", "team.accept_invite", ...
    target_id: str | None      # resource acted on
    ip: str | None             # X-Forwarded-For first hop
    user_agent: str | None     # X-User-Agent or request UA
    success: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    def write(self, adapter: SupabaseAdapter) -> None:
        adapter.insert("security_events", asdict(self))
```

---

## Testing Strategy

- **Unit (12 tests)**: `tests/test_security_validation.py` exercises every
  validator branch — default rejected, empty rejected, short rejected,
  dev override accepted.
- **Integration (6 tests)**: `tests/test_audit_log.py` drives a TestClient
  through signup, login (success + failure), accept-invitation, and
  asserts the rows in `security_events`.
- **RLS smoke (4 added)**: `tests/test_rls_smoke.py` validates that the
  service-role key can write but anon/authenticated users can only read
  the policies' filtered subset.
- **Regression**: full 302-test suite still green.
- **Coverage**: 92% target preserved (≥80% gate).

---

## Boundaries

**Always do:**
- Run `pytest -p no:randomly` before committing.
- Keep `Settings` field defaults **None** or empty for any secret; surface
  the requirement in the validator.
- New migrations are **additive** (no `DROP TABLE` of existing tables).
- Audit log writes are **best-effort** — they MUST NOT block the primary
  request. Failure to write an audit row returns 500 on the audit but
  the original response is already sent.

**Ask first:**
- Adding a new dep (e.g., `python-json-logger`).
- Changing `Settings` field types or names (breaks `.env`).
- Touching `migrations/001_init.sql` (cycle 1, frozen).

**Never do:**
- Commit a real secret, even in `.env.example`. Use `change-me` placeholders.
- Make audit-log writes blocking or transactional with the primary write.
  Audit should be a side-effect; the user's signup must succeed even if
  audit fails.
- Ship a `Settings` validator that swallows exceptions and logs a
  warning instead of raising. **Fail-fast or it doesn't ship.**

---

## Acceptance Criteria

- [ ] **AC-SEC-01** — `ENV=production` + `JWT_SECRET=dev-jwt-secret-change-me` →
      `Settings(...)` raises `ValueError` before `create_app()` runs.
- [ ] **AC-SEC-02** — `ENV=production` + `JWT_SECRET` < 32 bytes →
      raises with message including byte count.
- [ ] **AC-SEC-03** — `ENV=dev` + `JWT_SECRET=dev-jwt-secret-change-me` →
      succeeds (dev override).
- [ ] **AC-SEC-04** — `ENV=production` + `CORS_ORIGINS=["*"]` → raises.
- [ ] **AC-SEC-05** — `ENV=production` + `LINE_CHANNEL_SECRET=dev-...-change-me`
      → raises.
- [ ] **AC-SEC-06** — `ENV=production` + `STRIPE_API_KEY=sk_test_placeholder`
      when `USE_MOCKS=false` → raises.
- [ ] **AC-SEC-07** — `security_events` table created via
      `004_security_events.sql` with `id, actor_id, action, target_id,
      ip, user_agent, success, metadata, created_at`.
- [ ] **AC-SEC-08** — `POST /api/auth/signup` writes one row with
      `action='auth.signup', actor_id=<new user>, success=True`.
- [ ] **AC-SEC-09** — `POST /api/auth/login` writes one row on success
      (success=True) and one row on bad password (success=False).
- [ ] **AC-SEC-10** — `POST /api/teams/invitations/{token}/accept` writes
      one row with `action='team.accept_invite', target_id=<team_id>`.
- [ ] **AC-SEC-11** — RLS write policy on `team_invitations` allows
      team members to insert (not just service_role).
- [ ] **AC-SEC-12** — `docs/security.md` covers secret rotation
      (how to roll `JWT_SECRET` without logging everyone out), audit
      review (`SELECT * FROM security_events WHERE success = false`),
      and incident response.
- [ ] **AC-SEC-13** — All 12 new tests pass + 302 existing tests pass.

---

## Out of Scope

- **MFA / 2FA / WebAuthn** — cycle 6+
- **Rate limiting** — cycle 6 (e.g., `slowapi` or Redis token bucket)
- **Secret rotation tooling** — cycle 6 (one-shot JWT secret rollover)
- **SOC2 / ISO 27001 controls** — never (out of product scope)
- **OAuth provider integration** — out of scope (email/password only)
- **Front-end security headers** (CSP, HSTS) — cycle 6, owned by web
- **GDPR data export / right-to-delete** — cycle 7
- **Penetration testing** — separate engagement

---

## Open Questions

1. **Q: Should the validator also reject `JWT_SECRET` that equals the
   default `LINE_CHANNEL_SECRET`?** Both use the `change-me` placeholder
   pattern. Recommend: **no**, they're independent env vars and a deployer
   may use the same string for both. The validator already rejects the
   default value; whether two distinct defaults match by coincidence is
   not our concern.

2. **Q: Should the audit log be append-only (no UPDATE/DELETE policies)?
   Recommend: **yes** — security-events must be tamper-evident. Add RLS
   that only allows INSERT (service_role) and SELECT (team_id matching).

3. **Q: Audit failures — should they 500 the request or log-and-continue?
   Recommend: **log-and-continue**. The user's signup is more important
   than the audit row; an ops dashboard alerting on audit-write failures
   is the right pattern.

4. **Q: Should `dev` env be permissive enough that `pytest` works
   without an `.env` file? Recommend: **yes** — validators accept
   `dev-` prefix and `change-me` defaults; tests run against
   `env='test'` which inherits the dev exemption.

5. **Q: Does the cycle-3 `002_rls.sql` need updating, or do we
   add `004_security_events.sql`? Recommend: **additive only**. Cycle 3
   is frozen; the new audit-log table is `004_security_events.sql`.
   Existing RLS changes go in `005_rls_gaps.sql` if needed (T-507).