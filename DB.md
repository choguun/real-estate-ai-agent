**Detailed Database Schema Design**

**Database**: PostgreSQL (via Supabase)  
**Design Principles**:
- Optimized for Solo + Small Team use
- Strong focus on LINE integration and Lead management
- Support for AI-generated content
- PDPA compliance friendly (consent tracking, data retention)
- Clear relationships between entities

---

### Core Tables

#### 1. `users`
Stores real estate agents (both solo and team members).

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    phone TEXT,
    avatar_url TEXT,
    role TEXT CHECK (role IN ('owner', 'agent', 'admin')) DEFAULT 'agent',
    team_id UUID REFERENCES teams(id) ON DELETE SET NULL,
    line_user_id TEXT UNIQUE,                    -- LINE ID if connected
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX idx_users_team_id ON users(team_id);
CREATE INDEX idx_users_line_user_id ON users(line_user_id);
```

#### 2. `teams`
For small teams (1–5 people).

```sql
CREATE TABLE teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan TEXT CHECK (plan IN ('starter', 'growth', 'team')) DEFAULT 'starter',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
```

#### 3. `properties`
Core table for real estate listings.

```sql
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
    near_bts_mrt TEXT,                    -- e.g., "BTS Thong Lo"
    foreign_quota BOOLEAN DEFAULT false,
    
    status TEXT CHECK (status IN ('draft', 'active', 'sold', 'rented', 'archived')) DEFAULT 'draft',
    
    images JSONB,                         -- Array of image URLs
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_properties_user_id ON properties(user_id);
CREATE INDEX idx_properties_team_id ON properties(team_id);
CREATE INDEX idx_properties_status ON properties(status);
```

#### 4. `leads`
Potential buyers/renters (mainly from LINE).

```sql
CREATE TABLE leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    team_id UUID REFERENCES teams(id) ON DELETE SET NULL,
    
    name TEXT,
    phone TEXT,
    line_user_id TEXT,
    email TEXT,
    
    source TEXT DEFAULT 'line',           -- line, facebook, website, referral
    status TEXT CHECK (status IN ('new', 'contacted', 'qualified', 'viewing', 'negotiation', 'closed', 'lost')) DEFAULT 'new',
    interest_type TEXT,                   -- buy, rent
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
```

#### 5. `messages`
Stores all LINE conversations.

```sql
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID REFERENCES leads(id) ON DELETE SET NULL,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    direction TEXT CHECK (direction IN ('inbound', 'outbound')),
    message_type TEXT DEFAULT 'text',     -- text, image, sticker, etc.
    content TEXT,
    raw_data JSONB,                       -- Full LINE event payload
    
    is_ai_generated BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_messages_lead_id ON messages(lead_id);
CREATE INDEX idx_messages_user_id ON messages(user_id);
CREATE INDEX idx_messages_created_at ON messages(created_at);
```

#### 6. `appointments`
Viewing schedules.

```sql
CREATE TABLE appointments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    lead_id UUID REFERENCES leads(id) ON DELETE SET NULL,
    property_id UUID REFERENCES properties(id) ON DELETE SET NULL,
    
    scheduled_at TIMESTAMPTZ NOT NULL,
    duration_minutes INTEGER DEFAULT 60,
    status TEXT CHECK (status IN ('scheduled', 'completed', 'cancelled', 'no_show')) DEFAULT 'scheduled',
    notes TEXT,
    google_event_id TEXT,                 -- For Google Calendar sync
    
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_appointments_user_id ON appointments(user_id);
CREATE INDEX idx_appointments_lead_id ON appointments(lead_id);
CREATE INDEX idx_appointments_scheduled_at ON appointments(scheduled_at);
```

#### 7. `generated_listings`
Stores AI-generated listing content.

```sql
CREATE TABLE generated_listings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id UUID NOT NULL REFERENCES properties(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    platform TEXT CHECK (platform IN ('ddproperty', 'livinginsider', 'facebook', 'general')),
    title TEXT,
    description TEXT,
    hashtags TEXT[],
    seo_keywords TEXT[],
    
    ai_model TEXT,                        -- claude-3.5, gemini-2.0, etc.
    prompt_used TEXT,
    raw_response JSONB,
    
    is_published BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_generated_listings_property_id ON generated_listings(property_id);
```

#### 8. `contracts`
For storing contract drafts.

```sql
CREATE TABLE contracts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    property_id UUID REFERENCES properties(id) ON DELETE SET NULL,
    lead_id UUID REFERENCES leads(id) ON DELETE SET NULL,
    
    contract_type TEXT CHECK (contract_type IN ('sale', 'lease', 'reservation')),
    status TEXT CHECK (status IN ('draft', 'sent', 'signed', 'completed')) DEFAULT 'draft',
    
    content TEXT,                         -- Full contract text or HTML
    file_url TEXT,                        -- PDF URL
    signed_at TIMESTAMPTZ,
    
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
```

---

### Supporting Tables

#### 9. `user_settings`
For user/team preferences.

```sql
CREATE TABLE user_settings (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    default_property_type TEXT,
    notification_preferences JSONB,
    ai_model_preference TEXT DEFAULT 'claude-3.5',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
```

#### 10. `audit_logs` (Optional but recommended for compliance)
```sql
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
```

---

### Summary of Relationships

| Table              | Relationship                          | Type          |
|--------------------|---------------------------------------|---------------|
| `users`            | belongs to `teams`                    | Many-to-One   |
| `properties`       | belongs to `users` / `teams`          | Many-to-One   |
| `leads`            | belongs to `users` / `teams`          | Many-to-One   |
| `messages`         | belongs to `leads`                    | Many-to-One   |
| `appointments`     | links `leads` + `properties`          | Many-to-One   |
| `generated_listings` | belongs to `properties`             | Many-to-One   |
| `contracts`        | links `properties` + `leads`          | Many-to-One   |

---

### Recommended Supabase Configurations

- **Row Level Security (RLS)**: Enable on all tables. Users can only access their own data or their team’s data.
- **Indexes**: Already added on frequently queried columns (`user_id`, `status`, `created_at`).
- **Soft Delete**: Consider adding `deleted_at` column on `properties`, `leads`, and `contracts` for data retention compliance.
- **JSONB Fields**: Used for flexible data (`images`, `raw_data`, `notification_preferences`).

---

Would you like me to also provide:

1. **SQL script** ready to run in Supabase?
2. **RLS Policies** examples?
3. **Additional tables** (e.g., for commission tracking or analytics)?

Let me know how you want to proceed.