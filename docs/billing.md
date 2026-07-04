# Billing

Real Estate AI Agent (Thailand) uses **Stripe** for subscription
billing. The product is **mock-first** in dev/CI: the same backend
runs against `MockBillingAdapter` (in-memory, no network). In
production, flipping `USE_MOCKS=false` activates the real Stripe
adapter. This doc explains the model + the upgrade flow.

---

## 1. Pricing tiers

| Plan | Members | Properties | AI listings/mo | Monthly USD |
|------|---------|-------------|-----------------|-------------|
| `starter` | 1 | 5 | 20 | $0 (free) |
| `growth` | 3 | 25 | 200 | $29 |
| `team` | 10 | 100 | 1,000 | $99 |

`enterprise` — custom contract, Cycle 5+.

Every new signup lands on `starter` (free, 1 member max). The team
owner upgrades via the billing page; the limit raises immediately on
webhook receipt.

---

## 2. The flow

1. User visits `/dashboard/billing`, clicks **Upgrade to Growth**.
2. Frontend calls `POST /api/billing/checkout` with `{"plan": "growth"}`.
3. Backend creates a `billing_customers` row (if missing), then calls
   Stripe Checkout Session creation with `metadata.team_id`.
4. Frontend receives `{url, session_id}` and redirects the browser to
   Stripe's hosted checkout.
5. User enters card details (or uses Stripe test card `4242…`).
6. Stripe redirects back to `{frontend_url}/dashboard/billing?upgrade=success`.
7. Stripe sends a webhook to `POST /api/billing/webhook`.
8. Backend verifies the signature (`STRIPE_WEBHOOK_SECRET`),
   idempotency-checks on `stripe_event_id`, then updates
   `billing_customers.plan`, syncs `teams.plan`, and records the event.
9. Frontend polls `GET /api/billing/status` on the success page → seat
   limit is now 3 (growth).

---

## 3. Webhook events handled

| Event | Effect |
|-------|--------|
| `checkout.session.completed` | Upgrade team plan (per `metadata.plan`) |
| `customer.subscription.created` | Set `status='active'`, record `current_period_end` |
| `customer.subscription.updated` | Sync plan / status / cancel-at-period-end |
| `customer.subscription.deleted` | Revert to `starter`, `status='canceled'` |
| `invoice.payment_failed` | `status='past_due'` (team keeps working but can't add new members) |

All events are **idempotent**: the same `stripe_event_id` replayed
returns `{"status": "duplicate"}` without re-processing.

---

## 4. Mock vs real mode

`USE_MOCKS=true` (default for dev + CI) → `MockBillingAdapter`:
- In-memory `checkout`/`portal` sessions, recorded for tests
- Webhook accepts any JSON payload (no signature check)
- Returns stub URLs (`https://billing-mock.example.com/checkout/{token}`)
- All 4 methods covered by 11 unit tests in `tests/adapters/test_mock_billing.py`

`USE_MOCKS=false` (production) → `StripeBillingAdapter`:
- Wraps the official `stripe` Python SDK
- Webhook signature verified via `stripe.Webhook.construct_event`
  (HMAC-SHA256 against `STRIPE_WEBHOOK_SECRET`)
- `RUN_LIVE_BILLING=1` runs a live smoke test against Stripe **test mode**
  (no real money moves)

---

## 5. Plan limits

The `assert_can_invite` helper (in `app/services/plan_limits.py`) is
called from `POST /api/teams/{id}/invitations` BEFORE creating the
invitation row. It raises `PlanLimitExceeded` (HTTP 403) if the team
is at its seat cap.

| Plan | Seats | What happens on 4th invite (growth) |
|------|-------|--------------------------------------|
| starter | 1 | 403 `plan limit exceeded (seats): 1/1` |
| growth | 3 | 403 on the 4th invite attempt |
| team | 10 | 403 on the 11th invite attempt |

The check is **per-team, not per-user** — a team that grows from
starter → growth → team via the billing page sees its seat cap
increase immediately (no restart needed).

---

## 6. Payment failure (status='past_due')

When Stripe's `invoice.payment_failed` fires:
1. Webhook updates `billing_customers.status='past_due'`
2. Team can still log in + view their data
3. `assert_can_invite` still enforces the **current** plan's seat cap
4. Email notification to the team owner (T-407 future: SMTP via
   the email adapter)

To recover, the team owner opens the **Manage billing** button →
Stripe Customer Portal → updates their card. The next successful
invoice fires `invoice.paid` → status flips back to `active`.

---

## 7. Cancellation

- User clicks **Manage billing** → Stripe Portal → **Cancel plan**
- Stripe sends `customer.subscription.updated` with
  `cancel_at_period_end=true` and `current_period_end` set to the
  period's end
- Webhook updates `billing_customers.cancel_at_period_end=true`
- At `current_period_end`, Stripe sends
  `customer.subscription.deleted`
- Webhook reverts `teams.plan='starter'`, `status='canceled'`
- **Existing members are NOT removed** — they just can't invite new
  ones until the team upgrades again

---

## 8. Setup (production)

1. **Stripe dashboard**: create 2 products (Growth + Team) with monthly
   recurring prices. Copy each price_id.
2. **Stripe webhook**: point at
   `https://<your-api>/api/billing/webhook`. Subscribe to
   `checkout.session.completed`,
   `customer.subscription.created/updated/deleted`,
   `invoice.payment_failed`. Copy the signing secret.
3. **Set env vars** on Railway:
   ```
   USE_MOCKS=false
   STRIPE_API_KEY=sk_live_...
   STRIPE_WEBHOOK_SECRET=whsec_...
   STRIPE_PRICE_GROWTH=price_...
   STRIPE_PRICE_TEAM=price_...
   FRONTEND_URL=https://app.example.com
   ```
4. **Restart** the backend service. The factory rebuilds with the real
   adapter.
5. **Smoke test**: visit `/dashboard/billing`, click Upgrade, complete
   Stripe Checkout with a real card. Webhook fires → plan updates.

See [`docs/production-deploy.md`](./production-deploy.md) for the
full deploy walkthrough.

---

## 9. Why per-seat billing?

The Thai real estate market has a long tail of solo agents + small
boutiques (1-5 people). Per-seat is:
- **Fair** — solo agents pay $0, growing teams pay proportionally
- **Predictable** — no surprise overage charges
- **Self-service** — no sales calls; team owner clicks "Upgrade"

Per-property billing (a common alternative) is harder for a small
team because properties get sold/moved/archived — seat count is
more stable.

---

## 10. Related

- [`docs/production-deploy.md`](./production-deploy.md) — full env var list + Stripe setup
- `app/services/billing_service.py` — webhook handler (mock + real)
- `app/services/plan_limits.py` — seat guard
- `app/routers/billing.py` — the 4 routes
- `app/adapters/billing/{base,mock,real,_factory}.py` — the adapter
- `migrations/003_billing.sql` — `billing_customers` + `billing_events` tables
- `.aidlc/spec.md` — cycle 4 spec (AC-BL-01..12)
- `.aidlc/plan.md` — cycle 4 plan (T-401..T-407)
