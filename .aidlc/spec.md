# Spec: Cycle 4 — Per-Seat Billing + Stripe Webhooks

> **Status:** implementing
> **Branch:** `feat/billing-stripe`
> **Plan:** [`.aidlc/plan.md`](./plan.md) (T-401…T-407)

---

## Objective

Add a Stripe integration that turns the cycle-3 team model into a
monetizable SaaS. After this cycle, operators can pick a plan, pay
via Stripe Checkout, and have plan limits enforced. Webhooks keep
the team's `plan` field in sync with Stripe's subscription state.

**Who the user is:** a small Thai real estate agency (1-5 agents) who
outgrew the free tier and wants to pay for more seats / properties /
AI listings.

**Success = an operator can:**
1. Land on `/dashboard/billing`, click "Upgrade to Growth"
2. Stripe Checkout opens, returns to `/dashboard/billing?upgrade=success`
3. Webhook updates `team.plan = 'growth'` (mock in dev: button click)
4. `/api/billing/status` returns `{plan: 'growth', seats_used: 2, seats_limit: 3, ...}`
5. Enforce: can't invite a 4th member (403 PlanLimitExceeded)
6. Live smoke against Stripe **test mode** verifies the full loop

---

## Pricing tiers

| Plan | Members | Properties | AI listings/mo | Monthly USD |
|------|---------|-------------|-----------------|-------------|
| `starter` | 1 | 5 | 20 | $0 (free) |
| `growth` | 3 | 25 | 200 | $29 |
| `team` | 10 | 100 | 1,000 | $99 |

`enterprise` — custom contract, Cycle 5+

---

## Acceptance criteria

- [ ] **AC-BL-01** — `GET /api/billing/status` returns `{plan, status, seats_used, seats_limit, period_end, ...}`
- [ ] **AC-BL-02** — `POST /api/billing/checkout` creates Stripe Checkout session + returns `{url, session_id}` (mock returns stub URL)
- [ ] **AC-BL-03** — `POST /api/billing/portal` creates Stripe Customer Portal session
- [ ] **AC-BL-04** — `POST /api/billing/webhook` verifies HMAC-SHA256 signature in real mode; unsigned payloads accepted only in mock mode
- [ ] **AC-BL-05** — Webhook `checkout.session.completed` upgrades team plan; `customer.subscription.deleted` reverts to starter
- [ ] **AC-BL-06** — Plan-limit guard: free plan refuses 2nd member invitation (403 `PlanLimitExceeded`)
- [ ] **AC-BL-07** — Plan upgrade via webhook immediately raises the seat limit (no restart needed)
- [ ] **AC-BL-08** — Plan downgrade keeps existing memberships, blocks new invites until under the limit
- [ ] **AC-BL-09** — Frontend `/dashboard/billing` page renders pricing cards, plan badge, upgrade CTA
- [ ] **AC-BL-10** — Stripe test mode live smoke (RUN_LIVE_BILLING=1) creates a real checkout session
- [ ] **AC-BL-11** — `docs/billing.md` written (plans, limits, payment failure, cancel flow)
- [ ] **AC-BL-12** — Cycle-1+2+3 tests still pass (no regressions)

---

## Project structure (additions)

```
backend/app/
├── domain/billing.py                    # NEW: DTOs
├── services/
│   ├── billing_service.py              # NEW: start_checkout, handle_webhook
│   └── plan_limits.py                   # NEW: get_seat_limit, assert_can_invite
├── adapters/billing/                    # NEW category
│   ├── base.py                          # BillingAdapter Protocol
│   ├── mock.py                          # MockBillingAdapter (in-memory)
│   ├── real.py                          # StripeBillingAdapter (httpx + stripe SDK)
│   └── factory.py
├── routers/
│   └── billing.py                       # NEW: /api/billing/* endpoints
└── deps.py                              # update: BillingDep

backend/migrations/
└── 003_billing.sql                       # NEW: billing_customers

backend/tests/
├── test_billing.py                       # NEW (7 tests)
└── adapters/test_mock_billing.py         # NEW (6 tests)

web/lib/billing.ts                         # NEW
web/app/(app)/dashboard/billing/page.tsx  # NEW
web/components/billing/                   # NEW
docs/billing.md                           # NEW
```

---

## Test plan (ST-BL-NNN)

| ID | Title | Covers AC |
|---|---|---|
| ST-BL-01 | `GET /api/billing/status` returns team plan + seat counts | AC-BL-01 |
| ST-BL-02 | `POST /api/billing/checkout` returns URL + session_id | AC-BL-02 |
| ST-BL-03 | `POST /api/billing/portal` returns URL + session_id | AC-BL-03 |
| ST-BL-04 | Webhook verifies HMAC-SHA256 signature (real mode) | AC-BL-04 |
| ST-BL-05 | Webhook `checkout.session.completed` upgrades plan | AC-BL-05 |
| ST-BL-06 | Plan-limit guard: free plan refuses 2nd member | AC-BL-06 |
| ST-BL-07 | Plan upgrade via webhook immediately raises seat limit | AC-BL-07 |
| ST-BL-08 | Plan downgrade keeps existing memberships | AC-BL-08 |
| ST-BL-09 | Frontend `/dashboard/billing` renders pricing cards | AC-BL-09 |
| ST-BL-10 | Stripe test-mode live smoke (RUN_LIVE_BILLING=1) | AC-BL-10 |

---

## Out of scope (Cycle 5+)

- Stripe Tax / promo codes / annual pricing
- Per-property billing (we ship per-seat only)
- Stripe Connect (multi-vendor payouts)
- Plan refund handling (Stripe does, we just mirror status)
- Audit log UI for billing events (the `audit_logs` table is there)
- Real-time quota metering (we count on invite, not per-API-call)
- Multi-currency support (USD only for MVP)

---

## Open questions (resolved with defaults)

- **OQ-BL-A — Plan tier enforcement on what dimensions?** Per-seat
  (members) is the primary; properties + AI listings are secondary
  caps. Defaults: 1/3/10 members, 5/25/100 properties, 20/200/1000 AI
  listings/month. Listing cap resets monthly.
- **OQ-BL-B — Plan downgrade flow?** Default: prorated credit via
  Stripe; we just mirror `status='canceled'` + `cancel_at_period_end=true`.
  Existing members stay on (we don't revoke). Team plan field reverts
  to `starter` only at `current_period_end`.
- **OQ-BL-C — Free trial?** Default: 14-day Growth trial for new signups,
  no card required. Tracked in `billing_customers.status='trialing'` +
  `current_period_end = signup + 14d`.
- **OQ-BL-D — Refund policy?** Default: handled by Stripe dashboard;
  we don't auto-mirror refund events. Operators can manually downgrade.
- **OQ-BL-E — Plan pick on signup?** Default: NO — every new signup starts
  on `starter` (free). The team owner upgrades via `/dashboard/billing`
  when ready. Avoids Stripe Checkout friction during signup.

---

_Updated: 2026-07-04T05:00:00Z — Cycle 4 spec, plan in `.aidlc/plan.md`._
