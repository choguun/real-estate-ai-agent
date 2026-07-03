# Teams

Real Estate AI Agent (Thailand) supports **multi-tenant teams** so a
small real estate agency (2–5 agents) can share a property pool,
with cross-team isolation enforced at the DB level (Supabase RLS)
and the app level (mock adapter code filter).

This document explains:

1. The team model
2. How to create a team + invite a teammate
3. Roles + permissions
4. The security model (RLS)
5. Common operations

---

## 1. The team model

```
users (1) ─── (1) ─── team_memberships ─── (N) ─── (1) teams
                              │ role: owner | admin | agent
                              │
                              ├── (0..N) team_invitations (pending)
                              │
                              ├── (1) team_id column on:
                              │     properties, leads, messages,
                              │     generated_listings, contracts,
                              │     appointments, user_settings
```

- **MVP constraint**: a user is in **at most one** team.
  Cross-team membership is a Cycle 5+ feature.
- On signup (email or LIFF), a `Personal {uuid8}` team is auto-created
  so the team-scoped routers can resolve `team_id` without a separate
  `POST /api/teams` step. Users can later create additional teams
  via `POST /api/teams` (e.g. for a side-business).
- Every row in `properties`, `leads`, `messages`, `generated_listings`
  is scoped to the **team_id** that owns it.

---

## 2. How to create a team + invite a teammate

### From the web UI

1. Sign up at `/signup` — you'll be auto-assigned to a `Personal {x}`
   team.
2. Visit `/dashboard/team`.
3. Click **+ New team** → enter a name → team is created with you as
   `owner`.
4. Click **Invite member** → enter teammate's email + role → an email
   is sent (logged to dev console in mock mode) with a link like
   `https://app.example.com/invite/{token}`.
5. Teammate clicks the link → arrives at `/invite/{token}` → sees
   "Accept invitation" form. If they don't have an account yet, they
   set a password + name; if they do, the form is auto-filled.
6. On accept, they're added to the team with the invited role and
   auto-logged-in (a JWT is returned).

### From the API

```bash
# Create a team
curl -X POST https://api.example.com/api/teams \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Smith Realty"}'
# → {"id":"...","name":"Smith Realty","plan":"starter",...}

# Invite a teammate
curl -X POST https://api.example.com/api/teams/$TEAM_ID/invitations \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","role":"agent"}'
# → {"id":"...","token":"abc...","invite_url":"/invite/abc...",...}

# Alice accepts (she has no account yet)
curl -X POST https://api.example.com/api/teams/invitations/abc.../accept \
  -H "Content-Type: application/json" \
  -d '{"password":"supersecret123","full_name":"Alice"}'
# → {"access_token":"...","team_id":"...","user":{...}}
```

---

## 3. Roles + permissions

| Role | Invite | Change roles | Remove members | Leave team |
|------|--------|--------------|-----------------|-------------|
| `owner` | ✅ | ✅ | ✅ (any role except self) | ❌ (must delete or transfer) |
| `admin` | ❌ | ❌ | ✅ agents only | ✅ |
| `agent` | ❌ | ❌ | ❌ | ✅ |

**Critical invariants** (enforced in the router):
- An `owner` **cannot demote themselves** (would leave the team ownerless).
- An `owner` **cannot remove themselves** (must delete the team or
  transfer ownership — both Cycle 4+).
- A non-`owner` can `PATCH /api/teams/{id}/members/{user_id}` → 403.
- A non-`owner` can `DELETE /api/teams/{id}/members/{user_id}` → 403
  (except `admin` removing `agent`).

---

## 4. The security model — Supabase RLS

For the real Supabase path, **cross-team access is denied at the DB
level** by Row-Level Security policies declared in
`migrations/002_rls.sql`:

```sql
ALTER TABLE properties ENABLE ROW LEVEL SECURITY;
ALTER TABLE properties FORCE ROW LEVEL SECURITY;
CREATE POLICY team_isolation ON properties
    USING (team_id = auth_caller_team_id())
    WITH CHECK (team_id = auth_caller_team_id());
```

The `auth_caller_team_id()` SECURITY DEFINER function reads the
caller's `team_id` from the `users` table via the JWT `sub` claim.
This means even with a valid JWT, the application cannot read rows
outside the caller's team — the DB enforces the isolation.

The mock adapter does NOT use RLS — it simulates the same isolation
in code via `team_id` filters on every query.

### What RLS guarantees

- ✅ **Read isolation**: a user in team X cannot SELECT rows from team Y.
- ✅ **Write isolation**: a user in team X cannot INSERT/UPDATE/DELETE
  rows tagged with team Y's `team_id`.
- ✅ **Even service_role bypass is gated** via `FORCE ROW LEVEL SECURITY`
  on user tables (admins still need explicit team scoping).

### What RLS does NOT guarantee

- ❌ The application must still validate `team_id` before issuing
  commands. RLS prevents unauthorized access; it doesn't replace
  application-level validation.
- ❌ Users with the `service_role` key (used by the backend to
  bypass RLS for admin operations) can read/write anything. Protect
  this key like a database password.

---

## 5. Common operations

| Operation | Endpoint | Who |
|-----------|----------|-----|
| Get my team | `GET /api/teams/me` | Any auth'd user |
| Get my team members | `GET /api/teams/{id}/members` | Members of that team |
| Create a team | `POST /api/teams` | Any auth'd user |
| Invite a member | `POST /api/teams/{id}/invitations` | Owner only |
| Accept an invite | `POST /api/teams/invitations/{token}/accept` | Anyone (no auth) |
| Change a role | `PATCH /api/teams/{id}/members/{user_id}` | Owner only |
| Remove a member | `DELETE /api/teams/{id}/members/{user_id}` | Owner only |
| Leave a team | `POST /api/teams/{id}/leave` | Members (not owner) |

### What happens if I delete the only owner?

Currently: the team becomes "orphaned" — members can still access it
but there's no owner to manage it. Cycle 4+ will add:
- Team ownership transfer (`PATCH /api/teams/{id}/owner_id`)
- Team deletion with cascading archive

### What if the JWT contains a `team_id` claim?

The backend **does not** read `team_id` from the JWT. It always looks
up the user's current team from the `users` table. This is intentional
so that:
- A user can't escalate by forging a token with a different `team_id`.
- Rotating a user's team (Cycle 4+ feature) doesn't require re-issuing
  tokens.

---

## Related

- [`docs/adapters.md`](./adapters.md) — adapter architecture
- [`docs/architecture.md`](./architecture.md) — system overview
- [`docs/production-deploy.md`](./production-deploy.md) — bringing up
  the real services in production
- `backend/migrations/002_teams.sql` — schema migration
- `backend/migrations/002_rls.sql` — RLS policies
- `.aidlc/spec.md` — cycle 3 spec (AC-MT-01..12, ST-MT-01..12)
