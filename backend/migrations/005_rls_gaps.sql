-- 005_rls_gaps.sql — RLS write-path policies (cycle 5 T-504, AC-SEC-11)
--
-- Closes the cycle-3 review finding: 002_rls.sql enabled RLS on
-- team-scoped tables but only added SELECT policies. Team members
-- couldn't do common self-service operations via anon auth
-- (Supabase JWT, not the backend's service-role key):
--
--   - Team owner can't create an invitation via anon auth
--   - Team member can't leave the team (set left_at on their own row)
--
-- This migration adds the MINIMUM write policies that let team
-- members manage their own records, without compromising isolation:
--
--   team_invitations:   INSERT allowed if team_id = caller's team
--                       AND invited_by = caller. UPDATE/DELETE still
--                       service-role only.
--   team_memberships:   UPDATE allowed if user_id = auth.uid()
--                       (so a member can leave). INSERT/DELETE still
--                       service-role only.
--
-- billing_customers is intentionally NOT in this migration: the
-- Stripe webhook handler writes to it via service-role, and there
-- is no team-self-service flow that needs anon write. If a future
-- cycle adds a "team owner updates billing email" path, add the
-- policy then.
--
-- Apply order (matches the cycle-3 pattern):
--   1. Enable RLS + FORCE RLS (idempotent)
--   2. DROP POLICY IF EXISTS (idempotent)
--   3. CREATE POLICY
--
-- Mock note: the supabase mock does NOT enforce RLS — it simulates
-- the same isolation in code via team_id filters in the router
-- layer. This migration only takes effect when applied to a real
-- Postgres (Supabase).

-- ─── team_invitations: team member can insert for their own team ──
-- Service-role still owns UPDATE/DELETE (revoke, accept, etc.).
ALTER TABLE team_invitations ENABLE ROW LEVEL SECURITY;
ALTER TABLE team_invitations FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS team_invite_write ON team_invitations;
CREATE POLICY team_invite_write ON team_invitations
    FOR INSERT
    WITH CHECK (
        team_id = auth_caller_team_id()
        AND invited_by = auth.uid()
    );

-- ─── team_memberships: a member can leave via anon auth ────────────
-- Soft-delete: the UPDATE sets left_at to NOW(). The member can
-- only update their own row, not add or remove others.
ALTER TABLE team_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE team_memberships FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS team_membership_leave ON team_memberships;
CREATE POLICY team_membership_leave ON team_memberships
    FOR UPDATE
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

-- ─── notes on other tables intentionally left service-role only ──
-- teams:                  no team-self-service UPDATE flow today.
-- users:                  backend writes via service-role; anon-auth
--                         users don't self-update profiles in the
--                         web app (this is a multi-tenant admin tool,
--                         not a user-facing portal).
-- billing_customers:      webhook handler is service-role.
-- properties / leads / messages / generated_listings / contracts:
--                         all writes are service-role via the routers.
--                         If a future feature lets team members edit
--                         their own listings, add the policy then.