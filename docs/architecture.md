# Architecture

Real Estate AI Agent (Thailand) — Month-1 MVP. Two services, one database (mocked locally).

## Layers

```
┌─────────────────────────────────────────────────────────────┐
│                          web/ (Next.js 15)                   │
│  Server components · Client components · shadcn/ui-like     │
│  App router groups: (auth) (app)  (landing page at app root)  │
│  lib/: api.ts · auth.ts · dashboard.ts · leads.ts · listings.ts │
│       messages.ts · properties.ts · types.ts · uploads.ts · utils.ts │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTPS, JSON over HTTP, JWT bearer
                           │ (and multipart for image upload)
┌──────────────────────────▼──────────────────────────────────┐
│                       backend/ (FastAPI)                    │
│  Routers  : ai · auth · dashboard · health · leads ·         │
│             line_webhook · listings · messages · properties · │
│             storage                                          │
│  Services : auth · lead_pipeline · listing_generator        │
│  Domain   : user · property · listing · lead · message      │
│  Deps     : DBDep · StorageDep · AIChainDep · LineDep ·    │
│             SettingsDep · CurrentUserIdDep                   │
└──────────────────────────┬──────────────────────────────────┘
                           │ Protocol boundary
┌──────────────────────────▼──────────────────────────────────┐
│                app/adapters/{supabase,ai,line,storage}      │
│                                                             │
│  Each integration has TWO implementations behind one        │
│  Protocol. Mocks used in dev/tests by default; real         │
│  clients flip in via env flags (USE_MOCKS is the master   │
│  switch and overrides every USE_REAL_*).                   │
│                                                             │
│  { supabase │ ai │ line │ storage }                         │
│      ├── base.py        Protocol + DTOs                    │
│      ├── mock.py        in-memory / local-disk             │
│      ├── <real>.py      httpx to real service               │
│      └── _factory.py    picks by Settings flag              │
└─────────────────────────────────────────────────────────────┘
```

## Request lifecycle examples

### Form submit: agent adds a property

```
[Browser] /properties/new  (client component)
    │ POST /api/upload-image (image file → /static URL)
    │ POST /api/generate-listing (form fields → 4 Thai blocks)
    │ POST /api/properties   (create row scoped to user)
    │ POST /api/listings ×4   (save each variant)
    ▼
[FastAPI] routers/properties · routers/storage · routers/ai · routers/listings
    │ DBDep → MockSupabaseAdapter (singleton, in-process)
    │ StorageDep → LocalStorageAdapter (writes to backend/var/uploads/)
    │ AIChainDep → [AnthropicMockAdapter, GeminiMockAdapter]
    ▼
[Mock DB] rows visible to subsequent TestClient requests within the same process.
```

### Inbound LINE message (production-shape flow in MVP)

```
[LINE Cloud]  ── HTTPS POST /webhook/line with X-Line-Signature ──►  [FastAPI]
[FastAPI] routers/line_webhook
    1. read raw body bytes
    2. read X-Line-Signature header
    3. verify HMAC-SHA256 against settings.line_channel_secret
       (constant-time compare via hmac.compare_digest)
    4. JSON parse (only after verify)
    5. resolve agent_id (settings.line_default_agent_id OR first user)
    6. LeadPipeline.process_event(event, agent_id)
         • is_event_processed(event_id)        idempotency via message.raw_data scan
         • find-or-create lead by line_user_id
         • insert message (direction='inbound', raw_data=event)
         • bump lead.updated_at
    ▼
[Mock DB] leads + messages tables updated; eventually visible on /leads/[id].
```

### Outbound reply

```
[Browser] /leads/[id]  ComposeBox.send
    │ POST /api/leads/{lead_id}/messages  { text }
    ▼
[FastAPI] routers/messages
    1. scope lead by user_id
    2. require lead.line_user_id present
    3. line_adapter.send_reply(line_user_id, text)  (mock records; real calls LINE Reply API)
    4. insert message (direction='outbound', is_ai_generated=false)
    5. bump lead.updated_at
    ▼
[Browser] thread re-renders with the new bubble in the right column.
```

## Adapter Protocol contract

```
Router depends on:
    Protocol (db: SupabaseAdapter, ai: list[AiAdapter], …)

Adapter implements:
    The Protocol's method signatures

Switching:
    USE_* env flags (USE_REAL_SUPABASE / USE_REAL_AI / USE_REAL_LINE)
    _factory.get_X(settings) returns the right concrete class
    Routers never change
```

This pattern repeated four times keeps each integration isolated:
swap mocks for real services by editing `.env`, no code review needed.

## State management on the frontend

The web app has NO central store. Each page owns:
- `useEffect` for data fetching on mount
- `useState` for local form / message state
- 5 s polling on `/dashboard`
- localStorage for the JWT (`auth_token`)

A real backend would replace polling with WebSocket / SSE; the contract is unchanged.

## What's intentionally NOT here

- **Multi-tenant teams**: `teams` table exists; user-scoping RLS is on.
- **Cookie-based session**: localStorage + JWT only; HttpOnly cookies + CSRF would be the production migration.
- **WebSocket for chat**: 5 s polling is fine at MVP volume.
- **Image CDN**: local filesystem via `var/uploads/`. Swap is `_factory.storage`.
- **Google Calendar sync**: `appointments.google_event_id` is reserved but unused.

See `adapters.md` for the adapter-by-adapter map and `runbook.md` for the day-2 operations playbook.
