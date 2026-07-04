-- 004_security_events.sql — append-only audit log (cycle 5 T-502)
-- Mirrors the same shape as the mock adapter's _schema.py SECURITY_EVENTS
-- table. Applied on real Supabase via SQL editor or `supabase db push`.
-- Mock applies the same shape at startup.

-- ─── helper extensions (idempotent) ────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─── security_events (NEW — cycle 5) ────────────────────────────────────
-- Append-only audit log for security-relevant events:
--   auth.signup, auth.login, auth.login.failure, team.accept_invite,
--   billing.checkout, billing.portal, billing.payment_failed, ...
--
-- Schema notes:
--   actor_id:  NULL for anonymous actions (e.g., failed login where we
--              don't yet know who they are). Email goes into metadata.
--   action:    dotted-namespace action name (locked in app.audit_log).
--   target_id: resource acted on (team_id, user_id, ...). NULL if N/A.
--   success:   false = action was rejected / denied / failed.
--   metadata:  free-form JSONB for action-specific context.
--
-- ON DELETE SET NULL on actor_id: when a user is deleted (GDPR right-to-
-- erase, cycle 7), their historical audit rows survive but lose the actor
-- reference. We deliberately do NOT cascade-delete.

DROP TABLE IF EXISTS security_events CASCADE;

CREATE TABLE security_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    target_id UUID,
    ip TEXT,
    user_agent TEXT,
    success BOOLEAN NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_security_events_actor_id ON security_events(actor_id);
CREATE INDEX idx_security_events_action ON security_events(action);
CREATE INDEX idx_security_events_created_at ON security_events(created_at DESC);
CREATE INDEX idx_security_events_success_action
    ON security_events(success, action, created_at DESC)
    WHERE success = false;

-- ─── RLS policies (real Supabase only) ────────────────────────────────
-- Append-only at the database level: anyone authenticated can INSERT
-- (the backend uses service_role which bypasses RLS, but a future direct-
-- to-DB client should still be able to write); only the actor or their
-- team can SELECT. No UPDATE/DELETE policies → rows are immutable.
ALTER TABLE security_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE security_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS security_events_insert ON security_events;
CREATE POLICY security_events_insert ON security_events FOR INSERT
    WITH CHECK (true);

DROP POLICY IF EXISTS security_events_select ON security_events;
CREATE POLICY security_events_select ON security_events FOR SELECT
    USING (
        actor_id = auth.uid()
        OR target_id = auth_caller_team_id()
        OR auth.jwt()->>'role' = 'service_role'
    );
-- No UPDATE/DELETE policies → append-only at the DB level.