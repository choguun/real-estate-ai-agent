-- 002_teams.sql — multi-tenant teams + team_memberships
-- Builds on 001_init.sql. Idempotent (drops + recreates the new tables).
-- Mirrors DB.md and is applied on startup by the mock adapter (and
-- pasted into the Supabase SQL editor for the real path).

-- ─── helper extensions (idempotent) ───────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─── team_memberships (NEW) ─────────────────────────────────────────────
DROP TABLE IF EXISTS team_invitations CASCADE;
DROP TABLE IF EXISTS team_memberships CASCADE;

CREATE TABLE team_memberships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'agent')) DEFAULT 'agent',
    joined_at TIMESTAMPTZ DEFAULT now(),
    left_at TIMESTAMPTZ,
    removed_by UUID REFERENCES users(id),
    UNIQUE (team_id, user_id)
);
CREATE INDEX idx_team_memberships_team_id ON team_memberships(team_id);
CREATE INDEX idx_team_memberships_user_id ON team_memberships(user_id);
CREATE INDEX idx_team_memberships_role ON team_memberships(role);

-- ─── team_invitations (NEW) ─────────────────────────────────────────────
CREATE TABLE team_invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'agent')) DEFAULT 'agent',
    token TEXT UNIQUE NOT NULL,
    invited_by UUID NOT NULL REFERENCES users(id),
    invited_at TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    accepted_at TIMESTAMPTZ,
    accepted_by UUID REFERENCES users(id)
);
CREATE INDEX idx_team_invitations_team_id ON team_invitations(team_id);
CREATE INDEX idx_team_invitations_token ON team_invitations(token);
CREATE INDEX idx_team_invitations_email ON team_invitations(email);

-- ─── teams: enrich with plan timestamps + deleted_at (Cycle 4+ soft delete)
ALTER TABLE teams ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;

-- ─── RLS-enabling placeholders (real DDL lives in 002_rls.sql, T-305)
-- The mock adapter does NOT use RLS; it simulates the same isolation
-- in code via team_id filters. Real Supabase applies the RLS policies
-- at the DB level.

-- Mock-mirror note: the tables above are added to DEFAULT_SCHEMA in
-- app/adapters/supabase/_schema.py so the mock's schema check stays
-- in sync.
