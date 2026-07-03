-- 002_rls.sql — Supabase Row-Level Security policies (T-305)
-- Applied on real Supabase (paste in SQL editor or `supabase db push`).
-- The mock adapter does NOT use RLS — it simulates the same isolation
-- in code via team_id filters. This file is a no-op for the mock.
--
-- IMPORTANT: these policies assume JWT `sub` contains the user's UUID
-- (which is how the backend's auth.signup token is structured).
-- The service_role key bypasses RLS — server-side queries with
-- service_role can read everything (intentional, for admin tasks).
--
-- Apply in order:
-- 1. Enable RLS on each table
-- 2. Drop any pre-existing policy with the same name (idempotent)
-- 3. Create the policy
-- 4. Force RLS even for table owners (so no role bypasses accidentally)

-- ─── helper: function to get the caller's team_id from JWT sub ─────
CREATE OR REPLACE FUNCTION auth_caller_team_id() RETURNS UUID
LANGUAGE sql STABLE SECURITY DEFINER AS $$
    SELECT team_id FROM public.users WHERE id = auth.uid()
$$;

-- ─── properties ────────────────────────────────────────────────────
ALTER TABLE properties ENABLE ROW LEVEL SECURITY;
ALTER TABLE properties FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS team_isolation ON properties;
CREATE POLICY team_isolation ON properties
    USING (team_id = auth_caller_team_id())
    WITH CHECK (team_id = auth_caller_team_id());

-- ─── leads ──────────────────────────────────────────────────────────
ALTER TABLE leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE leads FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS team_isolation ON leads;
CREATE POLICY team_isolation ON leads
    USING (team_id = auth_caller_team_id())
    WITH CHECK (team_id = auth_caller_team_id());

-- ─── messages ──────────────────────────────────────────────────────
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS team_isolation ON messages;
CREATE POLICY team_isolation ON messages
    USING (team_id = auth_caller_team_id())
    WITH CHECK (team_id = auth_caller_team_id());

-- ─── generated_listings ───────────────────────────────────────────
ALTER TABLE generated_listings ENABLE ROW LEVEL SECURITY;
ALTER TABLE generated_listings FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS team_isolation ON generated_listings;
CREATE POLICY team_isolation ON generated_listings
    USING (team_id = auth_caller_team_id())
    WITH CHECK (team_id = auth_caller_team_id());

-- ─── users (read-only for team members) ────────────────────────────
-- A user can read their own row + rows of other users in the same team
-- (needed to render "John from Smith Realty" in lead attribution).
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE users FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS self_read ON users;
CREATE POLICY self_read ON users
    FOR SELECT
    USING (id = auth.uid() OR team_id = auth_caller_team_id());
-- No INSERT/UPDATE/DELETE policies → service_role only for those ops.

-- ─── team_memberships (users can see their own team's roster) ──────
ALTER TABLE team_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE team_memberships FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS team_roster_read ON team_memberships;
CREATE POLICY team_roster_read ON team_memberships
    FOR SELECT
    USING (team_id = auth_caller_team_id());
-- Writes still service_role only (router uses service_role key for
-- add/remove operations on team_memberships).

-- ─── teams (users can see their own team) ──────────────────────────
ALTER TABLE teams ENABLE ROW LEVEL SECURITY;
ALTER TABLE teams FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS team_self_read ON teams;
CREATE POLICY team_self_read ON teams
    FOR SELECT
    USING (id = auth_caller_team_id());
-- Writes service_role only.

-- ─── team_invitations (invitee + inviter can see; owner manages) ──
ALTER TABLE team_invitations ENABLE ROW LEVEL SECURITY;
ALTER TABLE team_invitations FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS invitation_read ON team_invitations;
CREATE POLICY invitation_read ON team_invitations
    FOR SELECT
    USING (team_id = auth_caller_team_id());
-- Writes service_role only.
