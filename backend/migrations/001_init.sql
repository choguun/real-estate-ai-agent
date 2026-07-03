-- ============================================================================
-- 001_init.sql — canonical schema for the real Supabase Postgres DB.
--
-- SOURCE OF TRUTH HIERARCHY:
--   1. /app/adapters/supabase/_schema.py — Python mirror used by the mock.
--   2. THIS FILE — canonical Postgres DDL executed against the real DB.
--   3. /DB.md — long-form doc (kept in sync manually).
--
-- KEEP IN SYNC: tests/adapters/test_mock_supabase.py::test_sql_matches_mock_schema
-- enforces that the SQL below and `_schema.py` declare the same tables.
-- ============================================================================

-- ─── Core tables ────────────────────────────────────────────────────────

CREATE TABLE teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan TEXT CHECK (plan IN ('starter', 'growth', 'team')) DEFAULT 'starter',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    phone TEXT,
    avatar_url TEXT,
    role TEXT CHECK (role IN ('owner', 'agent', 'admin')) DEFAULT 'agent',
    team_id UUID REFERENCES teams(id) ON DELETE SET NULL,
    line_user_id TEXT UNIQUE,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_users_team_id ON users(team_id);
CREATE INDEX idx_users_line_user_id ON users(line_user_id);

CREATE TABLE properties (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    team_id UUID REFERENCES teams(id) ON DELETE SET NULL,

    title TEXT,
    description TEXT,
    property_type TEXT CHECK (property_type IN ('condo', 'house', 'townhouse', 'land', 'commercial')),
    price NUMERIC(15,2),
    size_sqm NUMERIC(10,2),
    bedrooms INTEGER,
    bathrooms INTEGER,
    floor INTEGER,
    address TEXT,
    district TEXT,
    province TEXT,
    near_bts_mrt TEXT,
    foreign_quota BOOLEAN DEFAULT false,

    status TEXT CHECK (status IN ('draft', 'active', 'sold', 'rented', 'archived')) DEFAULT 'draft',

    images JSONB,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_properties_user_id ON properties(user_id);
CREATE INDEX idx_properties_team_id ON properties(team_id);
CREATE INDEX idx_properties_status ON properties(status);

CREATE TABLE leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    team_id UUID REFERENCES teams(id) ON DELETE SET NULL,

    name TEXT,
    phone TEXT,
    line_user_id TEXT,
    email TEXT,

    source TEXT DEFAULT 'line',
    status TEXT CHECK (status IN ('new', 'contacted', 'qualified', 'viewing', 'negotiation', 'closed', 'lost')) DEFAULT 'new',
    interest_type TEXT,
    budget_min NUMERIC(15,2),
    budget_max NUMERIC(15,2),
    preferred_areas TEXT[],

    notes TEXT,
    last_contacted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_leads_user_id ON leads(user_id);
CREATE INDEX idx_leads_status ON leads(status);
CREATE INDEX idx_leads_line_user_id ON leads(line_user_id);

CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID REFERENCES leads(id) ON DELETE SET NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    direction TEXT CHECK (direction IN ('inbound', 'outbound')),
    message_type TEXT DEFAULT 'text',
    content TEXT,
    raw_data JSONB,
    is_ai_generated BOOLEAN DEFAULT false,

    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_messages_lead_id ON messages(lead_id);
CREATE INDEX idx_messages_user_id ON messages(user_id);
CREATE INDEX idx_messages_created_at ON messages(created_at);

CREATE TABLE appointments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    lead_id UUID REFERENCES leads(id) ON DELETE SET NULL,
    property_id UUID REFERENCES properties(id) ON DELETE SET NULL,

    scheduled_at TIMESTAMPTZ NOT NULL,
    duration_minutes INTEGER DEFAULT 60,
    status TEXT CHECK (status IN ('scheduled', 'completed', 'cancelled', 'no_show')) DEFAULT 'scheduled',
    notes TEXT,
    google_event_id TEXT,

    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_appointments_user_id ON appointments(user_id);
CREATE INDEX idx_appointments_lead_id ON appointments(lead_id);
CREATE INDEX idx_appointments_scheduled_at ON appointments(scheduled_at);

CREATE TABLE generated_listings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    platform TEXT CHECK (platform IN ('ddproperty', 'livinginsider', 'facebook', 'general')),
    title TEXT,
    description TEXT,
    hashtags TEXT[],
    seo_keywords TEXT[],

    ai_model TEXT,
    prompt_used TEXT,
    raw_response JSONB,

    is_published BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_generated_listings_property_id ON generated_listings(property_id);

CREATE TABLE contracts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    property_id UUID REFERENCES properties(id) ON DELETE SET NULL,
    lead_id UUID REFERENCES leads(id) ON DELETE SET NULL,

    contract_type TEXT CHECK (contract_type IN ('sale', 'lease', 'reservation')),
    status TEXT CHECK (status IN ('draft', 'sent', 'signed', 'completed')) DEFAULT 'draft',

    content TEXT,
    file_url TEXT,
    signed_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- ─── Supporting tables ──────────────────────────────────────────────────

CREATE TABLE user_settings (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    default_property_type TEXT,
    notification_preferences JSONB,
    ai_model_preference TEXT DEFAULT 'claude-3.5',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    action TEXT NOT NULL,
    table_name TEXT,
    record_id UUID,
    old_data JSONB,
    new_data JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);
