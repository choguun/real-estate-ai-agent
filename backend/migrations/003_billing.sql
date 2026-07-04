-- 003_billing.sql — per-seat billing tables + trial tracking (T-401)
-- Mirrors the same shape as the mock adapter's _schema.py BILLING_CUSTOMERS
-- + BILLING_EVENTS tables. Applied on real Supabase via SQL editor
-- or `supabase db push`. Mock applies the same shape at startup.

-- ─── helper extensions (idempotent) ───────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─── billing_customers (NEW) ────────────────────────────────────────────
DROP TABLE IF EXISTS billing_events CASCADE;
DROP TABLE IF EXISTS billing_customers CASCADE;

CREATE TABLE billing_customers (
    team_id UUID PRIMARY KEY REFERENCES teams(id) ON DELETE CASCADE,
    -- Stripe identifiers — NULL until the team has ever started checkout
    stripe_customer_id TEXT UNIQUE,
    stripe_subscription_id TEXT UNIQUE,
    -- Local mirror of Stripe state (webhook keeps it in sync)
    plan TEXT NOT NULL DEFAULT 'starter'
        CHECK (plan IN ('starter', 'growth', 'team', 'enterprise')),
    status TEXT NOT NULL DEFAULT 'trialing'
        CHECK (status IN ('trialing', 'active', 'past_due', 'canceled', 'incomplete')),
    -- Subscription period boundaries (Stripe webhook sends these)
    current_period_start TIMESTAMPTZ,
    current_period_end TIMESTAMPTZ,
    cancel_at_period_end BOOLEAN NOT NULL DEFAULT false,
    -- Trial tracking (T-401 OQ-BL-C: 14-day Growth trial for new signups)
    trial_ends_at TIMESTAMPTZ,
    -- Audit
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_billing_customers_stripe_customer
    ON billing_customers(stripe_customer_id) WHERE stripe_customer_id IS NOT NULL;
CREATE INDEX idx_billing_customers_plan_status
    ON billing_customers(plan, status);

-- ─── billing_events (optional; for audit + replay) ──────────────────
CREATE TABLE billing_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID REFERENCES teams(id) ON DELETE CASCADE,
    stripe_event_id TEXT UNIQUE NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    received_at TIMESTAMPTZ DEFAULT now(),
    processed_at TIMESTAMPTZ
);
CREATE INDEX idx_billing_events_team_id ON billing_events(team_id);
CREATE INDEX idx_billing_events_received_at ON billing_events(received_at);

-- ─── teams: add plan-limits column for cheap plan-limit reads ────────
-- Avoids cross-table joins on every plan-limit check (T-404).
ALTER TABLE teams ADD COLUMN IF NOT EXISTS plan_limits JSONB;

-- ─── RLS policies (real Supabase only — mock has its own enforcement)
-- billing_customers is team-scoped, service-role manages it (writes
-- only happen in the webhook handler + webhook simulation).
ALTER TABLE billing_customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing_customers FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS billing_team_read ON billing_customers;
CREATE POLICY billing_team_read ON billing_customers
    FOR SELECT
    USING (team_id = auth_caller_team_id());
-- Writes service_role only.

ALTER TABLE billing_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE billing_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS billing_events_team_read ON billing_events;
CREATE POLICY billing_events_team_read ON billing_events
    FOR SELECT
    USING (team_id = auth_caller_team_id());
