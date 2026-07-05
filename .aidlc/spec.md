# Spec: Cycle 8 — TOTP MFA (Multi-Factor Authentication)

> **Status:** specifying
> **Branch:** `feat/mfa-totp`
> **Cycle origin:** Cycle-5 spec explicitly deferred MFA to cycle 7+.
> Cycle 7 didn't ship it; cycle 8 closes the gap.

---

## Objective

Today, the only auth factor is "something you know" (the password).
A stolen password = full account takeover. **MFA adds a second
factor — "something you have" (a TOTP code from an authenticator
app)** — that an attacker can't replay even if they have the
password.

Cycle 8 ships **TOTP-based MFA** (RFC 6238), the most universally
supported second factor:

- **TOTP** = Time-based One-Time Password. 6-digit codes that
  rotate every 30 seconds.
- **Authenticator app** = Google Authenticator, Authy, 1Password,
  Bitwarden, etc. (any app that supports the standard
  `otpauth://` URI).
- **Storage** = the TOTP secret is encrypted at rest with a
  Fernet key derived from a new env var (`MFA_ENCRYPTION_KEY`).

WebAuthn/FIDO2 (hardware keys, passkeys) is a stronger second
factor but requires browser FIDO2 support + a hardware token;
TOTP is the right first move. Cycle 9+ can add WebAuthn as a
layered option.

**Who the user is:** the Thai real-estate agency from cycles 1-7.
They want MFA so a compromised password doesn't end in account
takeover. Enterprise customers (in the cycle-7 per-team override
flow) may also want MFA-enforced-for-team in the future; cycle
8 ships the per-user mechanism, cycle 9+ adds per-team enforcement.

**Success = after cycle 8 ships:**

```bash
# 1. User enables MFA
# GET /api/auth/mfa/status → {enrolled: false}
# POST /api/auth/mfa/enroll → {secret: "JBSWY3DPEHPK3PXP", otpauth_url: "otpauth://..."}
# User scans QR in Google Authenticator
# POST /api/auth/mfa/verify {code: "123456"} → {ok: true, recovery_codes: ["abc-123", ...]}
# GET /api/auth/mfa/status → {enrolled: true}

# 2. Login flow requires TOTP after password
# POST /api/auth/login {email, password} → {mfa_required: true, mfa_token: "..."}  (if enrolled)
# POST /api/auth/login/mfa {mfa_token, code} → {token, user}     (verify TOTP)
#                                              OR {recovery_code: "abc-123"}  (use a recovery code)
# OR POST /api/auth/login {email, password, code: "123456"} → {token, user}     (one-step if code provided)

# 3. Brute-force protection on TOTP
# 5 wrong codes in 5 min → 429; reset on correct code
```

**Out of scope (explicit):**
- **WebAuthn / FIDO2 / passkeys** — cycle 9 (layered on top of TOTP;
  requires browser FIDO2 support + hardware token or platform
  authenticator)
- **Per-team MFA enforcement** (require-team-mfa policy) —
  cycle 9 (needs cycle-7's per-team override flow + a per-team
  `require_mfa` column)
- **SMS / email OTP** — explicitly out of scope (SIM-swap attacks
  on SMS; email is already a single-factor recovery channel)
- **OAuth provider integration** — out of scope (never)
- **GDPR data export** — cycle 9+ (separate product scope)

---

## Commands

```bash
# New tests
cd backend
pytest tests/test_mfa.py -v

# Full regression
pytest -p no:randomly  # 391 → ~420+ tests

# Lint / format / types
ruff check app tests
ruff format --check app tests
mypy app

# Frontend tests (MFA setup + verify pages)
cd ../web
npm test -- --run
```

---

## Project Structure

```
backend/
  app/
    mfa.py                       # NEW: TOTP + recovery code helpers
    audit_log.py                 # MOD: ACTION_MFA_ENROLLED/DISABLED/VERIFIED/FAILED
    config.py                    # MOD: add mfa_encryption_key
    security_validation.py       # MOD: validate_mfa_encryption_key()
    routers/
      auth.py                    # MOD: login flow returns mfa_required + mfa_token
      mfa.py                     # NEW: /api/auth/mfa/* endpoints
    services/
      auth.py                    # MOD: mfa_required + mfa_token flow
  migrations/
    007_mfa.sql                  # NEW: user_mfa + mfa_recovery_codes tables
  tests/
    test_mfa.py                  # NEW: 12 tests (enroll, verify, recovery,
                                #       login integration, brute-force protection)

web/
  app/
    (app)/dashboard/settings/
      mfa/page.tsx               # NEW: MFA setup page (QR + verify)
  lib/
    mfa.ts                       # NEW: client-side helpers
  __tests__/
    mfa.test.ts                  # NEW: 3 tests
  next.config.mjs                # (unchanged; CSP already in place)

docs/
  security.md                    # MOD: cycle-8 addendum (MFA ops)
```

---

## Code Style

Cycle 8 follows the cycle-5/6/7 patterns: thin pydantic models +
service layer + router glue.

**Good example (TOTP enrollment):**

```python
# app/mfa.py
import base64
import os
from cryptography.fernet import Fernet

def generate_totp_secret() -> str:
    """Generate a base32-encoded TOTP secret (160 bits per RFC 6238)."""
    raw = os.urandom(20)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def encrypt_secret(plaintext: str, *, fernet: Fernet) -> str:
    """Encrypt a TOTP secret for at-rest storage."""
    return fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(ciphertext: str, *, fernet: Fernet) -> str:
    """Decrypt a TOTP secret for verification."""
    return fernet.fernet.decrypt(ciphertext.encode("utf-8")).decode("ascii")
```

**Good example (MFA login flow):**

```python
# Login flow: after password check
if user.mfa_enrolled:
    # Issue a short-lived mfa_token (5 min) that the client exchanges
    # for a JWT after providing the TOTP code.
    mfa_token = create_mfa_token(user_id, settings)
    return {"mfa_required": True, "mfa_token": mfa_token}
# else: existing flow
return {"user": user, "token": create_access_token(...)}
```

---

## Testing Strategy

- **TOTP helpers (4 tests)** — generate secret shape, encrypt/decrypt
  round-trip, decrypt with wrong key raises
- **Enrollment (3 tests)** — POST /api/auth/mfa/enroll returns
  secret + otpauth URL; second enroll without disabling returns
  existing secret
- **Verify (3 tests)** — valid code marks user as enrolled + returns
  recovery codes; invalid code returns 401; brute-force after 5
  attempts returns 429
- **Login integration (2 tests)** — login with password returns
  mfa_required: true; login with password + TOTP returns full
  token; recovery code works as fallback
- **Recovery codes (2 tests)** — generated at enrollment, single-use,
  regenerated on disable+re-enroll
- **Audit log (2 tests)** — mfa.enrolled, mfa.disabled, mfa.failed
  rows in security_events
- **Regression**: 391 existing tests stay green
- **Coverage**: ≥ 90% preserved

---

## Boundaries

**Always do:**
- Run `pytest -p no:randomly` before committing
- TOTP secrets encrypted at rest with Fernet (symmetric)
- Recovery codes are single-use (deleted on consumption)
- Audit log every MFA event (enroll, verify, fail, disable, use-recovery)
- Rate-limit TOTP verify (5/min per user)
- Cycle-5 fail-fast validator runs on `MFA_ENCRYPTION_KEY` (≥ 32 bytes
  base64-encoded Fernet key in production)
- TOTP code window: ±1 step (90 seconds total) per RFC 6238 §5.2

**Ask first:**
- Adding a new dep (`cryptography` for Fernet, `pyotp` for TOTP)
- Changing `Settings` field types or names
- Touching `migrations/001_init.sql` (cycle 1, frozen)

**Never do:**
- Store TOTP secrets in plaintext (even in dev)
- Use a non-encrypted column for recovery codes (use a hash)
- Allow TOTP verification without a valid password first
- Skip the audit log on MFA events
- Reuse TOTP codes (RFC 6238 §5.2 recommends tracking used codes
  to prevent replay within the validity window)

---

## Acceptance Criteria

### TOTP enrollment

- [ ] **AC-MFA-01** — `migrations/007_mfa.sql` adds a `user_mfa` table
      with `user_id PRIMARY KEY, secret_encrypted TEXT, enrolled_at,
      last_used_at` + a `mfa_recovery_codes` table with
      `id, user_id, code_hash, used_at, created_at`. RLS: row visible
      only to the owning user.
- [ ] **AC-MFA-02** — `POST /api/auth/mfa/enroll` returns
      `{secret, otpauth_url, qr_url}` for the authenticated user.
      First call generates + stores; subsequent calls return the
      existing secret (idempotent).
- [ ] **AC-MFA-03** — The TOTP secret is encrypted at rest using
      Fernet with `Settings.mfa_encryption_key`. The plaintext
      secret is never written to the database.
- [ ] **AC-MFA-04** — `Settings.mfa_encryption_key` is a 32-byte
      URL-safe base64-encoded Fernet key. `validate_security()` (cycle
      5) enforces ≥ 32 bytes in production.

### TOTP verify + login flow

- [ ] **AC-MFA-05** — `POST /api/auth/mfa/verify {code}` with a
      valid 6-digit TOTP code marks the user as enrolled, returns
      10 single-use recovery codes, and writes `mfa.enrolled` to
      `security_events`.
- [ ] **AC-MFA-06** — `POST /api/auth/login {email, password}` for a
      user with `enrolled=true` returns `{mfa_required: true,
      mfa_token: "..."}` instead of a full JWT. The `mfa_token`
      is short-lived (5 min) and binds to the user_id.
- [ ] **AC-MFA-07** — `POST /api/auth/login/mfa {mfa_token, code}`
      (or `{mfa_token, recovery_code}`) returns the full JWT after
      verifying the TOTP code or recovery code.
- [ ] **AC-MFA-08** — `POST /api/auth/login {email, password, code}`
      is a one-step variant: if the user has MFA and the code is
      correct, return the full JWT directly. (Convenience for
      users who know their current TOTP code.)
- [ ] **AC-MFA-09** — 5 wrong TOTP codes within 5 minutes for the
      same user → 429 (rate-limited). On correct code, the rate
      limiter resets.
- [ ] **AC-MFA-10** — TOTP code is single-use within its 90-second
      validity window (replay protection per RFC 6238).

### Recovery codes

- [ ] **AC-MFA-11** — 10 recovery codes are generated at enrollment.
      Each is a 10-character alphanumeric string. Stored as a
      SHA-256 hash (never plaintext).
- [ ] **AC-MFA-12** — Recovery codes are single-use. `used_at` is
      set on consumption. Used codes return 401 on re-submit.
- [ ] **AC-MFA-13** — Re-enrollment (after `DELETE /api/auth/mfa`)
      regenerates the 10 recovery codes.

### Disable + audit

- [ ] **AC-MFA-14** — `DELETE /api/auth/mfa` requires the current
      TOTP code OR a recovery code (prevents an attacker with
      only the password from disabling MFA). Writes `mfa.disabled`
      to `security_events`.
- [ ] **AC-MFA-15** — Every MFA event writes to `security_events`:
      `mfa.enrolled`, `mfa.verified`, `mfa.failed`,
      `mfa.recovery_used`, `mfa.disabled`. Failed verifications
      include `metadata.attempted_code_length` (so dashboards
      can spot length-6 brute-force vs random typos).
- [ ] **AC-MFA-16** — `GET /api/auth/mfa/status` returns
      `{enrolled, recovery_codes_remaining}` for the
      authenticated user (lets the UI show "you have 8 codes
      left" before they run out).

### Frontend

- [ ] **AC-MFA-17** — `web/app/(app)/dashboard/settings/mfa/page.tsx`
      shows a QR code (rendered client-side from the otpauth URL)
      + a verify form. After verify, shows the 10 recovery codes
      with copy-to-clipboard.
- [ ] **AC-MFA-18** — The login page adds a step 2 (TOTP code
      input) when the response is `mfa_required: true`. The
      password → token flow is unchanged for non-MFA users.
- [ ] **AC-MFA-19** — 3 frontend tests: QR renders, verify form
      submits, recovery-code display.

### Docs + regression

- [ ] **AC-MFA-20** — `docs/security.md` adds a cycle-8 addendum
      covering MFA ops (lost-device recovery, recovery code
      rotation, brute-force detection via audit-log query).
- [ ] **AC-MFA-21** — All 391 existing tests still pass.
- [ ] **AC-MFA-22** — `pytest -p no:randomly` reports ≥ 415 tests
      (391 + ~24 new), ≥ 90% coverage.
- [ ] **AC-MFA-23** — `ruff check` + `ruff format --check` + `mypy
      app/` all clean.
- [ ] **AC-MFA-24** — `npm run typecheck` + `npm test` clean.

---

## Out of Scope

- **WebAuthn / FIDO2 / passkeys** — cycle 9 (layered on TOTP)
- **Per-team MFA enforcement** (require-team-mfa policy) —
  cycle 9 (uses cycle-7's per-team override flow + a per-team
  `require_mfa` column on `team_rate_limits` or a new
  `team_security_policies` table)
- **SMS / email OTP** — explicitly out of scope (SIM-swap, etc.)
- **OAuth provider integration** — out of scope (never)
- **GDPR data export** — cycle 9+ (separate product scope)
- **One-shot JWT rotation tool** — cycle 9 (cycle-7's manual
  4-step playbook works)
- **Split prod/dev deps** (cycle-7 review housekeeping) —
  cycle 9
- **Cycle-6 P2s** (`event_action: Literal[...]`, autouse fixture
  redundancy, `decode_token` rename) — cycle 9 polish

---

## Open Questions

1. **Q: Should the TOTP secret be visible to the user after
   enrollment (so they can re-add to a new device), or only
   shown once at enrollment?** Recommend: **only at enrollment**.
   Recovery codes are the second-factor reset path; the secret
   itself stays internal. Standard practice for TOTP.

2. **Q: Should the `mfa_token` (the short-lived token issued after
   password verify, exchanged for a JWT on TOTP verify) use the
   same JWT secret, or a separate secret?** Recommend: **same
   secret, different `aud` claim**. The mfa_token has a 5-min TTL
   and `aud="mfa"` so it can't be used to authenticate regular
   endpoints. Cycle-6's `decode_token_rotating` is reused.

3. **Q: For the TOTP `step` value (RFC 6238), use 30 seconds
   (default) or 60 seconds (more user-friendly)?** Recommend:
   **30 seconds**. Standard. Compatible with all major
   authenticator apps.

4. **Q: For the recovery code alphabet, use alphanumeric
   (a-zA-Z0-9) or lowercase + digits only (no I/0/1 confusion)?**
   Recommend: **lowercase + digits, ambiguous chars removed**
   (`crockford`-style: no I/L/O/0/1). 10 chars from 28-char
   alphabet = 28^10 ≈ 1.4e14 combinations per code; 10 codes
   per user = 1.4e15 total entropy. Strong enough.

5. **Q: For the brute-force protection, what's the rate limit?**
   Recommend: **5 wrong codes per 5 min per user_id** (not per
   IP — an attacker with the password also has the user_id from
   the response). Use the cycle-7 `RateLimiter` infra with a
   dedicated `mfa.verify` action.

6. **Q: For the frontend MFA setup page, where does it live?**
   Recommend: `web/app/(app)/dashboard/settings/mfa/page.tsx`
   (new settings sub-page). Linked from a "Security" section in
   the existing settings page.