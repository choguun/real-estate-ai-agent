-- 006_team_rate_limits.sql — per-team rate-limit overrides (cycle 7 T-702)
--
-- A team can override the system-default rate-limit policies (login
-- attempts per 15min, signups per hour, invitations per hour). A team
-- without an override row uses the system defaults.
--
-- Mirrors the cycle-4 billing_customers pattern: a separate table
-- keyed on team_id, with RLS so only the team owner can SELECT or
-- UPDATE their overrides. Mock applies the same shape at startup.

DROP TABLE IF EXISTS team_rate_limits CASCADE;

CREATE TABLE team_rate_limits (
    team_id UUID PRIMARY KEY REFERENCES teams(id) ON DELETE CASCADE,
    -- Per-action override. Each must be ≥ 1 (validated by the API;
    -- a CHECK constraint enforces it at the DB level too as defense
    -- in depth).
    login_per_15min INT NOT NULL DEFAULT 5 CHECK (login_per_15min >= 1),
    signup_per_hour INT NOT NULL DEFAULT 5 CHECK (signup_per_hour >= 1),
    invite_per_hour INT NOT NULL DEFAULT 20 CHECK (invite_per_hour >= 1),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_team_rate_limits_updated_at ON team_rate_limits(updated_at DESC);

-- ─── RLS policies (real Supabase only) ────────────────────────────────
-- Only the team's owner can SELECT or UPDATE their override row.
-- Mock simulates the same isolation in code.
ALTER TABLE team_rate_limits ENABLE ROW LEVEL SECURITY;
ALTER TABLE team_rate_limits FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS team_rate_limits_owner_read ON team_rate_limits;
CREATE POLICY team_rate_limits_owner_read ON team_rate_limits
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM team_memberships
            WHERE team_memberships.team_id = team_rate_limits.team_id
              AND team_memberships.user_id = auth.uid()
              AND team_memberships.role = 'owner'
              AND team_memberships.left_at IS NULL
        )
        OR auth.jwt()->>'role' = 'service_role'
    );

DROP POLICY IF EXISTS team_rate_limits_owner_write ON team_rate_limits;
CREATE POLICY team_rate_limits_owner_write ON team_rate_limits
    FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM team_memberships
            WHERE team_memberships.team_id = team_rate_limits.team_id
              AND team_memberships.user_id = auth.uid()
              AND team_memberships.role = 'owner'
              AND team_memberships.left_at IS NULL
        )
        OR auth.jwt()->>'role' = 'service_role'
    );

DROP POLICY IF EXISTS team_rate_limits_owner_insert ON team_rate_limits;
CREATE POLICY team_rate_limits_owner_insert ON team_rate_limits
    FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM team_memberships
            WHERE team_memberships.team_id = team_rate_limits.team_id
              AND team_memberships.user_id = auth.uid()
              AND team_memberships.role = 'owner'
              AND team_memberships.left_at IS NULL
        )
        OR auth.jwt()->>'role' = 'service_role'
    );

-- No DELETE policy → once an override exists, it's effectively
-- permanent (or until ON DELETE CASCADE removes the team itself).