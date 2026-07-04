# AIDLC State

- **Phase**: shipped
- **Branch**: main
- **PR**: #6 (merged 2026-07-04T17:38:21Z)
- **Last action**: 2026-07-04T17:38:21Z
- **Next action**: cycle 7 (MFA / WebAuthn OR Redis rate-limit backend)
- **Notes**:
  - 🎉 **Cycle 5 + cycle 6 shipped via PR #6 (squash-merged)**
  - Merged at `1b132ee` to main
  - **Cycle 5 (security hardening):**
    - T-501: Settings fail-fast validators (JWT/CORS/LINE/Stripe)
    - T-502: Audit log infra (security_events + RLS append-only)
    - T-503: Audit hooks in auth + teams + billing
    - T-504: RLS write-path policies (team_invitations INSERT +
      team_memberships UPDATE)
  - **Cycle 6 (rate limiting + rotation + headers):**
    - T-601: RateLimiter infra (Protocol + InMemory + Redis stub)
    - T-602: Auth rate-limit (login 5/15min, signup 5/hr per IP)
    - T-603: Invitation rate-limit (20/hr per owner)
    - T-604: JWT secret rotation (decode_token_rotating tries
      current + previous secret during rollover window)
    - T-605: Front-end security headers (CSP/HSTS/X-Frame-Options
      + Referrer-Policy + Permissions-Policy)
    - T-606: docs/security.md (operator runbook, 374 lines) +
      final verify
  - **Cycle-5 carry-over:** T-505 (docs/security.md) folded into
    cycle-6 T-606. Cycle-5 branch (`feat/security-hardening`)
    merged into cycle-6 at T-602 to share audit-log + RLS work.
  - **Final verification (post-cycle-6):**
    - Backend: 368 pass, 12 skipped, 0 failed ✅
    - Frontend: 40 vitest pass ✅
    - Coverage: ≥ 92% (preserves ≥ 80% gate) ✅
    - ruff + ruff-format + mypy strict: clean ✅
    - web typecheck (tsc): clean ✅
    - GitHub Actions CI: backend ✅ + frontend ✅
  - 21 ACs across 4 groups (AC-RL, AC-SR, AC-SEC, AC-WEB, AC-DOC)
    + 4 AC-REG all met
  - 17 commits squashed into 1 (PR #6 squash-merge)
  - Branch `feat/rate-limiting` deleted

_Updated: 2026-07-04T17:38:21Z_
- **Notes**:
  - 🎉 **Cycle 5 (security hardening: JWT/CORS defaults, audit log,
    RLS gaps) on feat/security-hardening — T-501..T-504 done; T-505
    (docs + final verify) folded into cycle 6's T-606**
    - 343 tests pass, ruff + mypy strict clean
    - Branch pushed but not PR'd yet (waiting for T-505/T-606)
  - 🚧 **Cycle 6 spec drafted** — rate limiting + secret rotation
    tooling + front-end security headers (CSP/HSTS/etc.)
    - 21 ACs (AC-RL-01..06, AC-SR-01..06, AC-WEB-01..05,
      AC-DOC-01, AC-REG-01..04)
    - 5 open questions (all recommendations logged)
    - Folds in T-505 from cycle 5 (docs/security.md) — saves a commit
  - **Branch**: feat/rate-limiting (cut from main after cycle 4's merge)
  - See commit `01a262f` for full spec.

_Updated: 2026-07-04T11:00:00Z_
