-- 007_mfa.sql — TOTP MFA tables (cycle 8 T-801, AC-MFA-01)
--
-- Adds two tables for Multi-Factor Authentication:
--   user_mfa: per-user TOTP enrollment (one row per enrolled user)
--   mfa_recovery_codes: 10 single-use recovery codes per enrollment
--
-- Both encrypted-at-rest patterns: the TOTP secret is stored as
-- a Fernet ciphertext (decryptable only with the production key);
-- recovery codes are stored as SHA-256 hashes (verifiable but
-- non-recoverable — the plaintext is shown once at enrollment).
--
-- Mirrors the cycle-4 billing_customers / cycle-7
-- team_rate_limits pattern: a separate table keyed on user_id
-- (or a related entity), with RLS so only the owning user
-- can read/write. Mock applies the same shape at startup.

DROP TABLE IF EXISTS mfa_recovery_codes CASCADE;
DROP TABLE IF EXISTS user_mfa CASCADE;

CREATE TABLE user_mfa (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    -- Fernet-encrypted TOTP secret. NEVER plaintext. Decryptable
    -- only with the production MFA_ENCRYPTION_KEY.
    secret_encrypted TEXT NOT NULL,
    enrolled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Track the last successfully-verified TOTP step for replay
    -- protection. The window is small (±1 step) so this just
    -- guards against immediate replay within a few seconds.
    last_verified_step INTEGER
);

CREATE TABLE mfa_recovery_codes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- SHA-256 hash of the recovery code (32 bytes hex). Plaintext
    -- is shown ONCE at enrollment; we can verify (re-hash on
    -- use) but never recover the plaintext.
    code_hash TEXT NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index for the common query: "find a user's recovery codes that
-- haven't been used yet" (for the count-remaining endpoint).
CREATE INDEX idx_mfa_recovery_codes_user_id
    ON mfa_recovery_codes(user_id, used_at)
    WHERE used_at IS NULL;

-- Index for the "find a specific code by its hash" lookup
-- (consume-a-code path).
CREATE INDEX idx_mfa_recovery_codes_code_hash
    ON mfa_recovery_codes(code_hash)
    WHERE used_at IS NULL;

-- ─── RLS policies (real Supabase only) ────────────────────────────────
-- Only the owning user can SELECT/INSERT/UPDATE/DELETE their
-- own MFA row. service_role bypasses for backend admin tasks.
ALTER TABLE user_mfa ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_mfa FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS user_mfa_owner_all ON user_mfa;
CREATE POLICY user_mfa_owner_all ON user_mfa
    FOR ALL
    USING (user_id = auth.uid() OR auth.jwt()->>'role' = 'service_role')
    WITH CHECK (user_id = auth.uid() OR auth.jwt()->>'role' = 'service_role');

ALTER TABLE mfa_recovery_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE mfa_recovery_codes FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS mfa_recovery_codes_owner_all ON mfa_recovery_codes;
CREATE POLICY mfa_recovery_codes_owner_all ON mfa_recovery_codes
    FOR ALL
    USING (user_id = auth.uid() OR auth.jwt()->>'role' = 'service_role')
    WITH CHECK (user_id = auth.uid() OR auth.jwt()->>'role' = 'service_role');