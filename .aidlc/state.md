# AIDLC State

- **Phase**: implementing
- **Branch**: feat/security-hardening
- **PR**: (TBD)
- **Last action**: 2026-07-04T10:35:00Z
- **Next action**: Run /implement T-502 (audit log infra)
- **Notes**:
  - 🎉 **Cycle 4 (per-seat billing + Stripe) shipped via PR #5**
  - Merged at `5ed76ba` to main
  - **T-401**: billing_customers + billing_events tables, RLS policies,
    teams.plan_limits JSONB column, 8 tests
  - **T-402**: BillingAdapter Protocol + MockBillingAdapter + 11 tests
  - **T-403**: /api/billing/* routes (status, checkout, portal, webhook),
    9 tests
  - **T-404**: plan-limit guard on invitations (PlanLimitExceeded), 8 tests
  - **T-405**: real StripeBillingAdapter (httpx + stripe SDK) + webhook
    signature verification + .env.example updates
  - **T-406**: frontend /dashboard/billing page + billing client
  - **T-407**: docs/billing.md (comprehensive guide)
  - **Post-review fix-ups** (5 cross-reviewer criticals, 6 commits):
    - C1 billing factory wiring (Settings.stripe_* → StripeBillingAdapter)
    - C1 sub-fix TeamCreate.plan = Literal["starter"] (no self-promotion)
    - C2 plan-limit guard added to /accept_invitation (POST + accept)
    - C3 JWT/CORS defaults (deferred to cycle 5 — explicitly out of scope)
    - C6 Stripe-Signature header always required (no USE_MOCKS fallback)
    - 5 new tests in test_real_billing.py + 1 in test_plan_limits.py
  - **Final verification (post-cycle-4):**
    - pytest: 302 pass, 12 skipped, 0 failed ✅
    - coverage: 92.36% (≥ 80% gate) ✅
    - ruff + ruff-format + mypy strict: clean ✅
    - vitest: 36/36 ✅
    - GitHub Actions CI: backend ✅ + frontend ✅
  - All 12 ACs (AC-BL-01..12) + 10 test scenarios (ST-BL-01..10) covered
  - 17 commits on feat/billing-stripe (now deleted)
  - **No existing router code changes** (T-304 invariant preserved) — billing
    router is purely additive; the only modified router was /teams for the
    accept-time plan-limit guard

- 🎉 **Cycle 5 spec drafted** — security hardening (fail-fast Settings
    validators for prod + audit log + RLS gap close). 13 ACs (AC-SEC-01..13),
    5 open questions (all recommendations logged).
  - **Files touched this commit:**
    - `.aidlc/spec.md` (rewritten for cycle 5)
  - See commit `a4be343` for full spec.

_Updated: 2026-07-04T10:30:00Z_
