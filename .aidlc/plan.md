# Plan: Month-1 MVP — Real Estate AI Agent (Thailand)

> **Phase:** planning
> **Branch:** `feat/month-1-mvp` · **PR:** #1
> **Source:** [`.aidlc/spec.md`](./spec.md) (12 ACs, 20 test scenarios)
> **Strategy:** 12 vertical slices, mostly sequential, each ends with a
> green test suite. Coverage target ≥ 80 % lines for `backend/app/`.

---

## Dependency Graph

```
T-001 ──▶ T-002 ──▶ T-003 ──▶ T-004 ──┬─▶ T-005 ──▶ T-006 ──▶ T-007 ──┐
   │          │          │          │                                    │
   │          │          │          ├─▶ T-008 ──▶ T-009 ──▶ T-010 ──────┤
   │          │          │          │                     │              │
   │          │          │          ▼                     ▼              ▼
   │          │          │       (storage)            (auth + leads)   (UI)
   │          │          └──────────────────────────────────────────────┘
   │          └──── (mock DB shared across all)
   └──── (CI gates every commit)

                                       ┌──▶ T-011 (dashboard)
                                       │       │
                                       ▼       ▼
                                  T-012 (E2E + docs)  ◀── depends on all
```

**Sequencing** is mostly linear because auth (T-003) gates every
authenticated route. The one parallelizable branch is **T-008 (LINE
webhook signature)** which is adapter-only and can be developed
alongside T-005–T-007. Inside those, T-005 (storage) does not need
T-006 (AI); they meet at T-007.

---

## Conventions for every task

- **RED → GREEN → REFACTOR** loop in every task (TDD). Implementer
  writes the failing test first, makes it pass, then cleans up.
- **Each task is independently committable** — the repo builds, lints,
  and tests green at every step. Never leave the tree red.
- **No horizontal slices.** Each task delivers a user-visible thing,
  even if small (an empty list page that fetches and renders is fine).
- **Mock-first.** Default `USE_MOCKS=true`; real adapters ship as
  stubs but are not required for tests to pass.

---

### T-001: Repo scaffold, FastAPI + Next.js shells, `/health` endpoints, CI

**Files:**
- `backend/pyproject.toml` (new)         — ruff + mypy + pytest config
- `backend/requirements.txt` (new)       — fastapi, uvicorn[standard], pydantic-settings, python-dotenv, pytest, httpx, ruff, mypy, bcrypt, PyJWT
- `backend/app/__init__.py` (new)
- `backend/app/main.py` (new)            — FastAPI factory, CORS, error handlers
- `backend/app/config.py` (new)          — pydantic-settings.BaseSettings
- `backend/app/routers/__init__.py` (new)
- `backend/app/routers/health.py` (new)  — `GET /health`
- `backend/tests/__init__.py` (new)
- `backend/tests/conftest.py` (new)      — TestClient fixture
- `backend/tests/test_health.py` (new)   — **ST-001**
- `backend/.env.example` (new)
- `web/package.json` (new)               — Next.js 15 deps
- `web/next.config.mjs` (new)
- `web/tsconfig.json` (new)
- `web/tailwind.config.ts` (new)
- `web/postcss.config.mjs` (new)
- `web/app/layout.tsx` (new)
- `web/app/page.tsx` (new)               — landing page that calls `/api/health`
- `web/app/api/health/route.ts` (new)    — proxy to backend `/health`
- `web/.env.example` (new)
- `web/components.json` (new)            — shadcn/ui config
- `.github/workflows/ci.yml` (new)       — lint + test matrix

**Description:**
Set up both packages to the point that `npm run dev` and `uvicorn
app.main:app --reload` run independently and the landing page can
fetch `/api/health` → `/health` → `{"status":"ok"}`. CI runs ruff +
pytest on the backend and lint + tsc on the frontend.

**Acceptance criteria:**
- [ ] `cd backend && uvicorn app.main:app --reload` starts on :8000
- [ ] `curl :8000/health` returns `{"status":"ok"}` (ST-001)
- [ ] `cd web && npm run dev` starts on :3000
- [ ] Landing page shows "Backend: ok" pulled via `/api/health`
- [ ] `ruff check` + `mypy --strict` pass
- [ ] `npm run lint` + `npm run typecheck` pass
- [ ] GitHub Actions workflow runs both matrices on PR

**Test approach:**
- pytest for `/health` (200, body shape, no auth).
- Skip Next.js page tests in this task (added in T-005/T-007).

**Estimated effort:** M

---

### T-002: Mock Supabase adapter + migration runner

**Files:**
- `backend/app/adapters/__init__.py` (new)
- `backend/app/adapters/supabase/__init__.py` (new)
- `backend/app/adapters/supabase/base.py` (new)        — `SupabaseAdapter` Protocol
- `backend/app/adapters/supabase/mock.py` (new)        — in-memory implementation
- `backend/app/adapters/supabase/real.py` (new)        — httpx client (stub for MVP; no real calls in tests)
- `backend/app/adapters/supabase/_schema.py` (new)     — schema definitions from `migrations/`
- `backend/migrations/__init__.py` (new)
- `backend/migrations/001_init.sql` (new)              — copy of `DB.md` schema
- `backend/app/deps.py` (new)                          — `get_db()` dependency selector
- `backend/tests/adapters/__init__.py` (new)
- `backend/tests/adapters/test_mock_supabase.py` (new) — CRUD round-trip per table (ST-020)
- `backend/tests/conftest.py` (edit)                   — schema-applied fixture per test

**Description:**
Every external integration lives behind a Protocol. The mock
implementation stores everything in process memory and applies
`migrations/001_init.sql` on startup (and per-test fixture). The real
client file exists as a stub — it implements the Protocol so the code
imports cleanly, but real-network code paths are not exercised in MVP.

**Acceptance criteria:**
- [ ] `SupabaseAdapter` Protocol defines: `query(table, filters)`, `insert(table, row)`, `update(table, id, patch)`, `delete(table, id)`
- [ ] Mock applies `001_init.sql` on startup; tables `users`,
      `properties`, `leads`, `messages`, `appointments`,
      `generated_listings`, `contracts`, `user_settings`, `audit_logs`
      exist with the columns from `DB.md`
- [ ] Round-trip CRUD works for at least 3 tables in tests (ST-020)
- [ ] `USE_REAL_SUPABASE=1` switches `get_db()` to the real client (no network calls in tests)
- [ ] Mock snapshot test: identical inputs → identical returned rows

**Test approach:**
- pytest, parametrized over tables.
- Each test scopes its own mock-DB fixture (re-applies migration → fast).

**Estimated effort:** M

---

### T-003: Auth (signup / login / LIFF), JWT, frontend `/login` + `/signup`

**Files:**
- `backend/app/domain/__init__.py` (new)
- `backend/app/domain/user.py` (new)              — `User` pydantic model
- `backend/app/services/__init__.py` (new)
- `backend/app/services/auth.py` (new)            — `hash_password`, `verify_password`, `create_access_token`, `decode_token`
- `backend/app/routers/auth.py` (new)             — POST /api/auth/{signup,login,liff}
- `backend/app/deps.py` (edit)                    — `CurrentUser` dep
- `backend/app/main.py` (edit)                    — register `auth` router
- `backend/tests/test_auth.py` (new)              — ST-002, ST-003, ST-004
- `web/lib/auth.ts` (new)                         — typed `login`, `signup`, `liffLogin`
- `web/lib/api.ts` (new)                          — fetch wrapper attaching `Authorization: Bearer <token>`
- `web/app/(auth)/layout.tsx` (new)
- `web/app/(auth)/login/page.tsx` (new)
- `web/app/(auth)/signup/page.tsx` (new)
- `web/components/forms/AuthForms.tsx` (new)      — both forms
- `web/__tests__/auth.test.ts` (new)              — `lib/auth.ts` happy paths

**Description:**
Three login paths land in one JWT. Passwords are bcrypt-hashed. LIFF
login is stubbed — clicking the LIFF button calls `POST /api/auth/liff`
with a fake `line_user_id` and gets back a session, no real OAuth in
MVP. JWT is signed with HS256 + a configurable secret; `CurrentUser`
dependency verifies it on every protected router.

**Acceptance criteria:**
- [ ] `POST /api/auth/signup` 200 + JWT for new email; 409 on duplicate (ST-002)
- [ ] `POST /api/auth/login` 200 + JWT for valid creds; 401 on bad password (ST-003)
- [ ] `POST /api/auth/liff` 200 + JWT, creates user keyed on `line_user_id` (ST-004)
- [ ] `GET /api/auth/me` returns current user when `Authorization` is valid; 401 otherwise
- [ ] `/login` and `/signup` pages work with shadcn forms
- [ ] LIFF button on `/login` calls the mock endpoint
- [ ] JWT bearer is sent on all subsequent API calls via `lib/api.ts`

**Test approach:**
- pytest: signup/login/LIFF/me with success + failure cases.
- vitest: `lib/auth.ts` types + token storage.

**Estimated effort:** M

---

### T-004: Properties domain + CRUD API + frontend list page

**Files:**
- `backend/app/domain/property.py` (new)         — `Property`, `PropertyType`, `PropertyStatus` enums
- `backend/app/routers/properties.py` (new)      — CRUD: list, create, get, update, archive
- `backend/app/main.py` (edit)                   — register router
- `backend/tests/test_properties.py` (new)       — ST-005
- `web/lib/types.ts` (new)                       — `Property` zod schema mirroring backend
- `web/app/(app)/layout.tsx` (new)               — auth-gated layout
- `web/app/(app)/properties/page.tsx` (new)      — server component fetching from backend
- `web/components/properties/PropertyCard.tsx` (new)
- `web/__tests__/api.test.ts` (new)              — `getProperties()` shapes

**Description:**
Authenticated agent can CRUD property records. The frontend `/properties`
page is a server component that renders cards with district/price/type.
Archive flips status to `archived` (soft delete — recoverable).

**Acceptance criteria:**
- [ ] CRUD all return correct status codes (200/201/204/404/422)
- [ ] Properties are scoped to `user_id` (cross-user reads return 404)
- [ ] `archived` properties hidden from default list endpoint
- [ ] `/properties` renders cards with title, district, price (formatted THB)

**Test approach:**
- pytest: CRUD cases + auth gate + cross-user 404.
- vitest: zod parse + THB formatter.

**Estimated effort:** M

---

### T-005: Mock storage adapter + property NEW form with image upload

**Files:**
- `backend/app/adapters/storage/__init__.py` (new)
- `backend/app/adapters/storage/base.py` (new)         — `StorageAdapter` Protocol
- `backend/app/adapters/storage/local_mock.py` (new)   — writes to `backend/var/uploads/`
- `backend/app/adapters/storage/supabase_real.py` (new) — stub for MVP
- `backend/app/routers/storage.py` (new)               — POST /api/upload-image
- `backend/app/main.py` (edit)                         — register router + mount `/static` for mock
- `backend/tests/test_storage.py` (new)                — ST-015
- `backend/app/routers/properties.py` (edit)           — accept `images: list[str]`
- `web/app/(app)/properties/new/page.tsx` (new)
- `web/components/forms/PropertyForm.tsx` (new)
- `web/components/forms/ImageUploader.tsx` (new)
- `web/__tests__/propertyForm.test.tsx` (new)          — ST-016 (preview shown)

**Description:**
Storage abstraction lets the mock adapter write to disk and the real
one upload to Supabase Storage. The frontend `PropertyForm` includes a
file picker that previews thumbnails and uploads on submit.

**Acceptance criteria:**
- [ ] `POST /api/upload-image` accepts `multipart/form-data`, persists under `var/uploads/{uuid}.{ext}`, returns absolute URL (ST-015)
- [ ] Returned URL serves the file via `GET /static/{filename}` → 200 + correct MIME (ST-020)
- [ ] `PropertyForm` shows upload progress + preview (ST-016)
- [ ] Submitting form with images persists URLs to `properties.images`

**Test approach:**
- pytest: upload happy path + extension guard.
- vitest/RTL: form preview state.

**Estimated effort:** M

---

### T-006: Mock AI adapter + generate-listing endpoint + integrate into form

**Files:**
- `backend/app/adapters/ai/__init__.py` (new)
- `backend/app/adapters/ai/base.py` (new)             — `AiAdapter` Protocol: `generate_listing(property, platform) -> GeneratedContent`
- `backend/app/adapters/ai/anthropic_mock.py` (new)   — deterministic Thai templates
- `backend/app/adapters/ai/anthropic_real.py` (new)   — stub for MVP (offline)
- `backend/app/adapters/ai/gemini_mock.py` (new)
- `backend/app/adapters/ai/gemini_real.py` (new)      — stub
- `backend/app/services/listing_generator.py` (new)   — picks adapter by env, applies fallback chain
- `backend/app/domain/listing.py` (new)               — `GeneratedListing` model + `Platform` enum
- `backend/app/routers/ai.py` (new)                   — POST /api/generate-listing
- `backend/app/main.py` (edit)                        — register router
- `backend/tests/test_ai_generator.py` (new)          — ST-006, ST-007
- `web/components/forms/ListingPreview.tsx` (new)     — shows 4 platform tabs
- `web/app/(app)/properties/new/page.tsx` (edit)     — add "Generate" button

**Description:**
The mock AI adapter returns Thai text templated by property type and
platform. Latency is bounded (≤2 s in mock mode). The frontend form
gets a "Generate" button that calls the API and renders four tabs
(DDProperty, Livinginsider, Facebook, General).

**Acceptance criteria:**
- [ ] `POST /api/generate-listing` returns four `GeneratedContent`
      blocks with Thai fields (ST-006)
- [ ] Condo inputs produce text containing "คอนโด" + "ตร.ม." (ST-006)
- [ ] House inputs mention "บ้านเดี่ยว" or "บ้าน" (ST-007)
- [ ] Mock response includes hashtags for Facebook (≥ 5 hashtags)
- [ ] Anthropic configured but errors → falls back to Gemini (via
      `listing_generator` service) without leaking internal errors
- [ ] Latency p99 ≤ 2 s in mock mode
- [ ] Render 4 platform tabs in `ListingPreview`

**Test approach:**
- pytest: per-property-type fixtures, per-platform assertions,
  substring checks, latency budget assertion.

**Estimated effort:** M

---

### T-007: Generated listing persistence + property DETAIL page with editor

**Files:**
- `backend/app/routers/listings.py` (new)               — POST /api/listings, GET /api/listings?property_id, PATCH /api/listings/{id}
- `backend/app/domain/listing.py` (edit)                — add `GeneratedListingInDB`
- `backend/app/main.py` (edit)                          — register router
- `backend/tests/test_ai_generator.py` (edit)           — ST-008
- `web/app/(app)/properties/[id]/page.tsx` (new)
- `web/components/forms/ListingEditor.tsx` (new)
- `web/lib/api.ts` (edit)                               — `saveListing`, `getListings`

**Description:**
Once a generated listing is shown in the form, the user can save it to
the `generated_listings` table. Saved listings live on the property
detail page; each is editable in place and supports multiple platform
variants for the same property.

**Acceptance criteria:**
- [ ] `POST /api/listings` inserts a row, returns `id`
- [ ] `GET /api/listings?property_id=...` returns all variants for that property
- [ ] `PATCH /api/listings/{id}` updates editable fields
- [ ] Property detail page renders one card per platform variant (ST-008)
- [ ] Saving from `/properties/new` redirects to `/properties/{id}`

**Test approach:**
- pytest: insert/list/update + per-user isolation.
- vitest/RTL: editor state.

**Estimated effort:** M

---

### T-008: Mock LINE adapter + webhook signature verification

**Files:**
- `backend/app/adapters/line/__init__.py` (new)
- `backend/app/adapters/line/base.py` (new)             — `LineAdapter` Protocol
- `backend/app/adapters/line/mock.py` (new)             — in-memory event store + signer
- `backend/app/adapters/line/real.py` (new)             — stub for MVP
- `backend/app/routers/line_webhook.py` (new)           — POST /webhook/line
- `backend/app/main.py` (edit)                          — register router
- `backend/tests/test_line_webhook.py` (new)            — ST-009, ST-010
- `backend/app/services/__init__.py` (already created)

**Description:**
Mock LINE adapter allows tests to submit signed events and inspect
what replies were sent. Real adapter file ships as a stub — structure
present, no real HTTP. The webhook handler verifies `X-Line-Signature`
via HMAC-SHA256 using `LINE_CHANNEL_SECRET` BEFORE parsing the body.

**Acceptance criteria:**
- [ ] Mock adapter signs payloads with a configurable channel secret
- [ ] `POST /webhook/line` with valid signature → 200 (ST-009)
- [ ] Same request with mutated signature → 401 (ST-010)
- [ ] Same request missing header → 401
- [ ] Verification happens BEFORE body parse (security property)

**Test approach:**
- pytest: signature positive/negative cases, header-presence cases,
  parity with `line-bot-sdk` reference signature.

**Estimated effort:** M

---

### T-009: LINE → Lead + Message pipeline (idempotent)

**Files:**
- `backend/app/domain/lead.py` (new)              — Lead model
- `backend/app/domain/message.py` (new)            — Message model
- `backend/app/services/lead_pipeline.py` (new)    — `process_event(event) -> ProcessResult`
- `backend/app/routers/line_webhook.py` (edit)     — call pipeline
- `backend/tests/test_line_webhook.py` (edit)      — ST-011, ST-012

**Description:**
`process_event` takes a verified LINE event, dedupes by `event_id`,
upserts a Lead by `line_user_id`, and inserts a Message with direction
`inbound`. Replays return early. The same `line_user_id` across
multiple events always hits the same lead.

**Acceptance criteria:**
- [ ] First message from new `line_user_id` creates exactly 1 Lead + 1 Message (ST-012)
- [ ] Second message from same user: 0 Leads created, 1 new Message, same lead id
- [ ] Replay (same `event_id`): 0 Leads, 0 new Messages, 200 OK (ST-011)
- [ ] Pipeline never throws on malformed events; logs and returns processed=false

**Test approach:**
- pytest: replay + multi-message cases; per-test event-id reset.

**Estimated effort:** M

---

### T-010: Lead listing + per-lead chat UI + outbound reply via mock LINE

**Files:**
- `backend/app/routers/leads.py` (new)             — GET /api/leads, GET /api/leads/{id}, PATCH /api/leads/{id}
- `backend/app/routers/messages.py` (new)          — POST /api/leads/{id}/messages (outbound via LINE adapter)
- `backend/app/routers/line_webhook.py` (edit)     — outbound path plumbing
- `backend/tests/test_leads.py` (new)
- `web/app/(app)/leads/page.tsx` (new)             — list with status filters
- `web/app/(app)/leads/[id]/page.tsx` (new)        — chat thread
- `web/components/chat/MessageList.tsx` (new)
- `web/components/chat/ComposeBox.tsx` (new)        — uses `lib/api.ts` send

**Description:**
Agent views leads and per-lead conversations; sending a reply from the
UI hits the backend which (in mock mode) records the outbound
`direction='outbound'` Message and (in mock mode) surfaces via the
mock LINE adapter. In real mode, it would call LINE Reply API.

**Acceptance criteria:**
- [ ] `/api/leads` paginated, filterable by status
- [ ] `/api/leads/{id}` includes all messages, sorted ascending
- [ ] POST reply creates an outbound Message with `is_ai_generated=false`
- [ ] `/leads` page shows status pills + last contact time
- [ ] `/leads/[id]` renders inbound (left) and outbound (right) messages

**Test approach:**
- pytest: lead pagination + per-user scoping + reply round-trip.
- vitest/RTL: chat layout snapshot.

**Estimated effort:** M

---

### T-011: Dashboard endpoint + page (recent messages, properties, lead counter)

**Files:**
- `backend/app/routers/dashboard.py` (new)         — GET /api/dashboard
- `backend/tests/test_dashboard.py` (new)           — ST-013
- `web/app/(app)/dashboard/page.tsx` (new)
- `web/components/dashboard/RecentMessages.tsx` (new)
- `web/components/dashboard/RecentProperties.tsx` (new)
- `web/components/dashboard/NewLeadsCounter.tsx` (new)
- `web/__tests__/dashboard.test.tsx` (new)          — ST-014

**Description:**
Single endpoint aggregates what the homepage needs: last 20 inbound
messages, last 5 properties, count of leads with status `new`. Polled
every 5 s client-side in MVP (no WebSocket).

**Acceptance criteria:**
- [ ] `/api/dashboard` returns all three blocks (ST-013)
- [ ] Page renders all three in a grid
- [ ] Counter badge shows count, dims to 0 when no new leads

**Test approach:**
- pytest: aggregation logic + scoping per user.
- vitest: empty-state rendering.

**Estimated effort:** S

---

### T-012: Playwright E2E happy path, real-adapter swap test, architecture docs

**Files:**
- `web/playwright.config.ts` (new)
- `web/tests/e2e/happy-path.spec.ts` (new)          — ST-018
- `backend/tests/test_real_swap.py` (new)           — ST-019 (skipped by default)
- `backend/tests/adapters/test_mock_ai_snapshots.py` (new) — ST-020
- `docs/architecture.md` (new)
- `docs/adapters.md` (new)
- `docs/runbook.md` (new)
- `.github/workflows/ci.yml` (edit)                  — run Playwright headless
- `README.md` (edit)                                 — link to docs

**Description:**
End-to-end test signs up, creates a property with a fake image upload,
generates a listing, saves it, opens the detail page. Real-adapter
swap is verified by importing the real client modules and asserting
they implement the same Protocol (no network calls). Docs cover
architecture, the adapter contract, and a deploy runbook.

**Acceptance criteria:**
- [ ] Playwright spec runs green headless in CI (ST-018)
- [ ] `python -c "from app.adapters.supabase.real import ..."` imports cleanly and satisfies `isinstance(..., SupabaseAdapter)` (ST-019)
- [ ] Coverage report shows ≥ 80 % lines for `app/`
- [ ] Three docs exist and link from `README.md`

**Test approach:**
- Playwright headless on a single browser.
- `pytest --cov=app --cov-fail-under=80`.
- `coverage` XML written + uploaded as CI artefact.

**Estimated effort:** M

---

## Coverage map (AC ↔ Task ↔ Scenario)

| AC      | T-001 | T-002 | T-003 | T-004 | T-005 | T-006 | T-007 | T-008 | T-009 | T-010 | T-011 | T-012 |
|---------|:-----:|:-----:|:-----:|:-----:|:-----:|:-----:|:-----:|:-----:|:-----:|:-----:|:-----:|:-----:|
| AC-01   |   ●   |   ●   |   ●   |       |       |       |       |       |       |       |       |   ●   |
| AC-02   |   ●   |       |       |       |       |       |       |       |       |       |       |       |
| AC-03   |       |       |   ●   |       |       |       |       |       |       |       |       |       |
| AC-04   |       |       |       |   ●   |       |       |       |       |       |       |       |       |
| AC-05   |       |       |       |       |       |   ●   |       |       |       |       |       |       |
| AC-06   |       |       |       |       |       |       |   ●   |       |       |       |       |       |
| AC-07   |       |       |       |       |       |       |       |   ●   |       |       |       |       |
| AC-08   |       |       |       |       |       |       |       |       |   ●   |   ●   |       |       |
| AC-09   |       |       |       |       |       |       |       |       |       |       |   ●   |       |
| AC-10   |       |       |       |       |   ●   |       |       |       |       |       |       |       |
| AC-11   |       |       |       |       |       |       |       |       |       |       |       |   ●   |
| AC-12   |       |   ●   |       |       |       |       |       |       |       |       |       |   ●   |

---

## After this plan

1. Commit: `git add .aidlc/ && git commit -m "plan: 12 vertical slices for Month-1 MVP"`
2. Push to update PR #1
3. `aidlc` next → `/implement T-001`

_Updated: 2026-07-03T06:35:00Z_
