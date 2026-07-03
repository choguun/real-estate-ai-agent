# Spec: Cycle 3 — Multi-Tenant Teams with RLS

> **Status:** implementing
> **Branch:** `feat/multi-tenant-teams`
> **Plan:** [`.aidlc/plan.md`](./plan.md) (T-301…T-308)

---

## Objective

Light up multi-tenant teams end-to-end: a small real estate agency
(2-5 agents) can share a property pool, with cross-team isolation
enforced at the DB level (Supabase RLS) and at the app level (mock
adapter code filter).

**Who the user is:** a Thai real estate agency owner who has outgrown
the single-tenant MVP. Wants to invite 1-4 teammates, share the
property/lead/message pool, and have a per-team dashboard.

**Success = a deployed user can:**

1. Create a team (becomes `owner`)
2. Invite a teammate by email (mock email log in dev)
3. Teammate accepts the invite → gets a JWT + team-scoped access
4. Either user can list team properties / leads / messages
5. A user in team X CANNOT see team Y's data (404 or empty list)
6. On real Supabase: RLS denies cross-team access at the DB level

---

## Acceptance criteria

- [ ] **AC-MT-01** — `POST /api/teams` creates a team + sets caller as `owner`
- [ ] **AC-MT-02** — `GET /api/teams/me` returns caller's team(s)
- [ ] **AC-MT-03** — `POST /api/teams/{id}/invitations` generates a token (≥32 bytes entropy, 7-day TTL)
- [ ] **AC-MT-04** — `POST /api/teams/invitations/{token}/accept` creates user (if new) + adds to team + returns JWT
- [ ] **AC-MT-05** — Cross-team isolation: user in team X sees only team X's properties/leads/messages
- [ ] **AC-MT-06** — Within-team: any member can see any other member's properties/leads
- [ ] **AC-MT-07** — Owner can change roles + remove members; admin can remove agents; agent can leave
- [ ] **AC-MT-08** — Owner cannot demote or remove themselves
- [ ] **AC-MT-09** — Supabase RLS policies enforce cross-team isolation at the DB level (live smoke)
- [ ] **AC-MT-10** — Frontend `/dashboard/team` page renders roster + invite UI
- [ ] **AC-MT-11** — Existing 230 tests adapted to team-scoping (no regressions)
- [ ] **AC-MT-12** — `docs/teams.md` written (how teams work, how to invite, security model)

---

## Project structure (additions)

```
backend/app/
├── domain/
│   └── team.py                       # NEW: Team DTOs, Invitation DTOs
├── services/
│   ├── team_service.py               # NEW: create_team, list_members, etc.
│   └── invitation_service.py         # NEW: token gen, accept, expiry
├── routers/
│   └── teams.py                      # NEW: /api/teams/* endpoints
├── adapters/
│   └── email/                        # NEW category
│       ├── base.py                   # EmailAdapter Protocol
│       ├── mock.py                   # MockEmailAdapter (console log)
│       ├── real.py                   # RealEmailAdapter stub
│       └── factory.py
└── deps.py                          # update: get_current_team()

backend/migrations/
├── 002_teams.sql                     # NEW: team_memberships table
└── 002_rls.sql                       # NEW: RLS policies (real Supabase)

web/
├── app/(app)/dashboard/team/
│   └── page.tsx                       # NEW: team settings page
├── components/team/
│   ├── InviteMemberModal.tsx         # NEW
│   └── MemberRow.tsx                  # NEW
├── lib/team.ts                        # NEW: typed team API client
└── __tests__/team.test.tsx            # NEW
```

---

## Test plan (ST-MT-NNN)

| ID | Title |
|---|---|
| ST-MT-01 | `POST /api/teams` creates team + caller is owner |
| ST-MT-02 | `GET /api/teams/me` returns caller's team(s) |
| ST-MT-03 | `GET /api/teams/{id}/members` lists all members + roles |
| ST-MT-04 | Cross-team isolation: team X user sees 0 team Y properties |
| ST-MT-05 | Within-team: any member can see any other member's properties |
| ST-MT-06 | Owner can change roles + remove members |
| ST-MT-07 | Owner cannot demote/remove themselves |
| ST-MT-08 | Invite token generation: ≥32 bytes entropy, 7-day expiry |
| ST-MT-09 | Accept invite: creates user (if new) + adds to team + returns JWT |
| ST-MT-10 | RLS live smoke: real Supabase denies cross-team read |
| ST-MT-11 | Frontend `/dashboard/team` renders roster + invite modal |
| ST-MT-12 | All 230 existing tests pass after re-scoping |

---

## Out of scope (Cycle 4+)

- Per-seat billing
- Audit log UI (schema exists; no reader page yet)
- Granular per-resource roles
- Team-scoped LINE OA (multi-OA per team)
- Team ownership transfer
- Real email service (Resend / SendGrid / SES)
- Team deletion
- Production observability (Sentry / OpenTelemetry)
- CRM analytics
- i18n beyond Thai + English
- Mobile app, native LINE Flex Messages
- Contract generation / e-signature / PDF export
- Google Calendar two-way sync

---

## Open questions (resolved with defaults)

- **OQ-MT-A — Plan tier on team creation?** Default: `starter` (free tier,
  single team). Future billing cycle can upgrade via Stripe webhook.
- **OQ-MT-B — Multi-team membership?** Default: NO — a user is in at
  most one team. Simpler scoping. Cross-team is a Cycle 5+ feature.
- **OQ-MT-C — Invitation re-use after acceptance?** Default: NO — once
  accepted, the token is invalidated (410 Gone on re-use).
- **OQ-MT-D — Owner can delete team?** Default: NO in this cycle. Adds
  cascade-delete complexity + reassignment. Cycle 4+.

---

_Updated: 2026-07-04T01:30:00Z — Cycle 3 spec, plan in `.aidlc/plan.md`._
