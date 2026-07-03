# Month-1 MVP — Real Estate AI Agent (Thailand)

> **Status:** specifying (AIDLC phase 1)
> **Branch:** `feat/month-1-mvp`
> **Source materials:** [`../PLAN.md`](../../PLAN.md), [`../DB.md`](../../DB.md), answers Q1–Q7

---

## Objective

Ship a single-agent, mock-first MVP of a Thai real estate SaaS that
solves two problems in one product:

1. **Lead capture from LINE** — every Thai buyer/renter messages the
   agent on LINE first; the MVP turns that firehose into a structured
   inbox with auto-created leads and full message history.
2. **Listing generation with AI** — the agent fills a one-form property
   brief, the system returns a ready-to-post Thai listing
   (DDProperty / Livinginsider / Facebook variants).

**Who the user is:** a solo Thai real estate agent who already uses LINE
as their primary messaging channel and spends 30+ minutes per listing
copy-pasting from English templates into Thai portals.

**Success = a clone of this repo, with no API keys, can:**
- run both apps locally,
- walk through one full end-to-end flow via the UI,
- pass every test in the test plan below,
- swap mock adapters for real LINE / Supabase / Anthropic adapters by
  flipping env flags — no code change.

---

## Commands

All commands run from the repo root unless noted. Use the worktree
path if working inside the AIDLC worktree.

### Setup (one-time per machine)

```bash
# Frontend (Node 20+)
cd web
npm install
cp .env.example .env.local

# Backend (Python 3.11+)
cd backend
python3.11 -m venv venv
source venv/bin/activate
pip install -U pip
pip install -r requirements.txt
cp .env.example .env
```

### Development

```bash
# Run backend (FastAPI on :8000)
cd backend && source venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Run frontend (Next.js on :3000)
cd web
npm run dev

# End-to-end smoke (after both apps are up)
curl http://localhost:8000/health             # → {"status":"ok"}
open http://localhost:3000                     # landing page
```

### Quality gates

```bash
# Backend
cd backend && source venv/bin/activate
ruff check app/ tests/                         # lint
ruff format app/ tests/                        # format
mypy app/                                      # type-check
pytest -q --cov=app --cov-fail-under=80        # tests + coverage ≥80%

# Frontend
cd web
npm run lint                                   # eslint
npm run typecheck                              # tsc --noEmit
npm test                                       # vitest unit
npm run test:e2e                               # playwright e2e (after T-012)
```

### Deploy

```bash
# Frontend → Vercel
vercel --prod                                  # uses web/vercel.json

# Backend → Railway
railway up                                     # uses backend/railway.toml
railway variables set USE_MOCKS=false SUPABASE_URL=…  # flip to real
```

---

## Project Structure

```
real-estate-ai-agent/                          # repo root
├── README.md
├── LICENSE
├── PLAN.md                       # roadmap (Month 1–N)
├── DB.md                         # canonical schema
├── .gitignore
│
├── .aidlc/                       # AIDLC state + artifacts
│   ├── state.md                  # current phase, branch, PR
│   ├── spec.md                   # this file
│   └── plan.md                   # T-001 … T-012
│
├── docs/                         # long-form docs (added by T-013)
│   ├── architecture.md
│   ├── adapters.md
│   └── runbook.md
│
├── web/                          # Next.js 15 frontend (App Router)
│   ├── app/
│   │   ├── (marketing)/page.tsx                       # landing
│   │   ├── (auth)/login/page.tsx
│   │   ├── (auth)/signup/page.tsx
│   │   ├── (app)/dashboard/page.tsx
│   │   ├── (app)/properties/page.tsx                 # list
│   │   ├── (app)/properties/new/page.tsx             # form + AI gen
│   │   ├── (app)/properties/[id]/page.tsx            # edit + variants
│   │   ├── (app)/leads/page.tsx                       # list
│   │   ├── (app)/leads/[id]/page.tsx                  # chat
│   │   ├── (app)/settings/page.tsx
│   │   ├── api/health/route.ts
│   │   └── layout.tsx
│   ├── components/
│   │   ├── ui/                    # shadcn/ui generated
│   │   ├── forms/PropertyForm.tsx
│   │   ├── forms/ListingEditor.tsx
│   │   ├── chat/MessageList.tsx
│   │   └── chat/ComposeBox.tsx
│   ├── lib/
│   │   ├── api.ts                 # typed fetch client
│   │   ├── auth.ts                # Supabase auth + LIFF mock
│   │   └── types.ts               # shared DTOs (zod schemas)
│   ├── tests/                     # vitest + playwright
│   ├── public/
│   ├── .env.example
│   ├── next.config.mjs
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   └── package.json
│
└── backend/                       # FastAPI service
    ├── app/
    │   ├── main.py                # FastAPI factory, CORS, error handlers
    │   ├── config.py              # pydantic-settings, reads .env
    │   ├── deps.py                # DI: db, current_user, line_adapter, ai_adapter
    │   ├── domain/                # pydantic DTOs, enums, value objects
    │   │   ├── user.py
    │   │   ├── property.py
    │   │   ├── lead.py
    │   │   ├── message.py
    │   │   └── listing.py
    │   ├── adapters/              # ★ all integrations behind interfaces
    │   │   ├── supabase/
    │   │   │   ├── base.py
    │   │   │   ├── mock.py        # in-memory store + Postgres schema applier
    │   │   │   └── real.py        # httpx → Supabase REST
    │   │   ├── line/
    │   │   │   ├── base.py
    │   │   │   ├── mock.py        # in-memory event bus + signed payloads
    │   │   │   └── real.py        # httpx → LINE Reply API
    │   │   ├── ai/
    │   │   │   ├── base.py
    │   │   │   ├── anthropic_mock.py
    │   │   │   ├── anthropic_real.py
    │   │   │   ├── gemini_mock.py
    │   │   │   └── gemini_real.py
    │   │   └── storage/
    │   │       ├── base.py
    │   │       ├── local_mock.py  # writes to ./var/uploads
    │   │       └── supabase_real.py
    │   ├── routers/               # FastAPI routers
    │   │   ├── health.py
    │   │   ├── auth.py            # /api/auth/signup, /login, /liff
    │   │   ├── properties.py      # /api/properties (CRUD)
    │   │   ├── leads.py           # /api/leads (CRUD, status update)
    │   │   ├── messages.py        # /api/messages (per-lead inbox)
    │   │   ├── line_webhook.py    # /webhook/line (signature-verified)
    │   │   ├── ai.py              # /api/generate-listing
    │   │   ├── storage.py         # POST /api/upload-image
    │   │   └── dashboard.py       # GET /api/dashboard
    │   └── services/              # domain orchestration
    │       ├── lead_pipeline.py   # raw LINE msg → Lead + Message
    │       └── listing_generator.py
    ├── migrations/                # SQL files referenced by mock + real
    │   └── 001_init.sql           # mirrors DB.md exactly
    ├── tests/
    │   ├── conftest.py            # spins up TestClient with mock adapters
    │   ├── test_health.py
    │   ├── test_auth.py
    │   ├── test_properties.py
    │   ├── test_leads.py
    │   ├── test_line_webhook.py
    │   ├── test_ai_generator.py
    │   ├── test_storage.py
    │   ├── adapters/test_mock_supabase.py
    │   ├── adapters/test_mock_line.py
    │   └── adapters/test_mock_ai.py
    ├── var/                       # gitignored: uploads + mock DB state
    ├── pyproject.toml             # ruff + mypy + pytest config
    ├── requirements.txt
    ├── .env.example
    ├── Dockerfile                 # for Railway
    └── railway.toml
```

### Why this structure

- **`web/` and `backend/`** — two top-level packages so they can be
  deployed independently to Vercel and Railway without monorepo tooling.
- **`backend/app/adapters/`** — single homed point for every external
  integration. Every adapter implements an `Adapter` Protocol so the
  router code is adapter-agnostic. To swap mocks for real services,
  set `USE_MOCKS=false` (or per-adapter flags) — no other code change.
- **`backend/migrations/`** — raw SQL (the same files run in Supabase's
  SQL editor) so the mock and real databases share an exact schema.
- **`backend/var/`** — runtime uploads + mock DB snapshot. Gitignored.

---

## Code Style

### Backend (Python 3.11+)

**Good example** — `app/routers/health.py`:

```python
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness probe.

    Returns:
        dict with key "status" = "ok" if the service is up. No auth.
    """
    return {"status": "ok"}
```

- `from __future__ import annotations` everywhere.
- Type hints on **every** public function; `-> dict[str, str]` not `dict`.
- Pydantic v2 models for every DTO. Use `model_config = ConfigDict(extra="forbid")`.
- Logging: `get_logger(__name__)`, never `print()`.
- Errors: raise domain exceptions, map to HTTP in a single handler
  (`app/main.py::register_exception_handlers`).
- Lint/format/typecheck: ruff + ruff-format + mypy strict.

**DO NOT** — common pitfalls:

```python
# BAD: mutable default + no types
def update_user(data={}):
    data["x"] = 1
    return data

# BAD: global state
DB = {}

# BAD: catching Exception
try:
    ...
except Exception:           # too broad
    pass
```

### Frontend (TypeScript, Next.js 15 App Router)

**Good example** — `app/(app)/properties/page.tsx`:

```tsx
import { getProperties } from "@/lib/api";

export default async function PropertiesPage() {
  const properties = await getProperties();
  return (
    <ul className="grid gap-4 sm:grid-cols-2">
      {properties.map((p) => (
        <li key={p.id} className="rounded border p-4">
          <h2 className="font-medium">{p.title ?? "Untitled"}</h2>
          <p className="text-sm text-muted-foreground">{p.district}</p>
        </li>
      ))}
    </ul>
  );
}
```

- Server Components by default; mark `"use client"` only when needed.
- Named exports for utilities; default exports for page/layout files.
- Validation at edges with zod schemas that mirror backend DTOs.
- shadcn/ui primitives in `components/ui/` — don't rewrite them.
- Tailwind utilities; no CSS modules unless shared with shadcn.

### Shared style (both)

- **No secrets in code.** Anything that varies per environment goes in
  `.env` and is loaded via `app/config.py` (backend) or `process.env`
  (frontend, with the `NEXT_PUBLIC_` prefix only when truly public).
- **Adapter boundary = the only place that may use a third-party SDK.**
  Routers and services import from `app.adapters.<x>.base`, never
  directly from `anthropic`/`line-bot-sdk`/`@supabase/supabase-js`.

---

## Testing Strategy

| Layer        | Tooling              | What it covers                                        | Where it lives                       |
|--------------|----------------------|-------------------------------------------------------|--------------------------------------|
| Backend unit | pytest + httpx       | adapters, services, domain, signature verification   | `backend/tests/adapters/`, `app/services/` |
| Backend API  | pytest TestClient    | every router endpoint, status code + body contract   | `backend/tests/test_*.py`            |
| Frontend unit| vitest + RTL         | components, hooks, `lib/api.ts`                       | `web/__tests__/`                     |
| Frontend e2e | Playwright           | one full happy-path flow from signup to listing save | `web/tests/e2e/`                     |
| Mocks parity | pytest, snapshot     | mock responses are **stable** so swapping is safe    | `backend/tests/adapters/test_mock_*.py` |

**Coverage target:** ≥80 % lines for `app/` (excluding `adapters/*_real.py`,
which depend on live services).

**Test pyramid rules:**

- Every adapter has at least one test against the mock + one against
  the real client (real client tests are skipped unless `RUN_REAL_ADAPTER_TESTS=1`).
- Every router has at least one happy-path test + one auth-failure test.
- One Playwright spec covers the full user journey (signup → property
  → AI listing → save → see in dashboard).
- No test deletes an actual Supabase row, sends a real LINE message,
  or charges Anthropic.

---

## Boundaries (in-scoped rules)

### Always do

- ✅ Run `ruff check` + `mypy` + `pytest` before committing Python.
- ✅ Run `npm run lint && npm run typecheck && npm test` before committing TS.
- ✅ Use the adapter interface, not a third-party SDK directly, anywhere
  outside `app/adapters/`.
- ✅ Verify LINE webhook signature with HMAC-SHA256 against the channel
  secret before parsing the payload.
- ✅ Idempotency: dedupe LINE events by `(event_id)` and ignore replays.
- ✅ Commit `.aidlc/state.md` updates within the same commit as the
  phase work.
- ✅ Use Thai property terminology in AI prompts:
  *คอนโด*, *ทาวน์เฮาส์*, *บ้านเดี่ยว*, *ที่ดิน*, *ห้องนอน*, *ห้องน้ำ*,
  *ตร.ว.* (sq. wah), *ตร.ม.* (sqm), BTS/MRT proximity phrasing.
- ✅ Use PDPA-safe defaults: never log raw message bodies at INFO;
  log only metadata + truncated hashes.

### Ask first

- 🟡 Adding a new top-level dependency (`pip` or `npm`).
- 🟡 Adding a new adapter outside the existing four categories.
- 🟡 Changing the canonical DB schema (`backend/migrations/*.sql`).
- 🟡 Changing the LINE webhook URL or signature scheme.
- 🟡 Changing the deploy targets or adding a new one (Cloud Run, Fly).

### Never do

- ⛔ Commit secrets, real channel tokens, API keys, or `.env` files.
- ⛔ Skip the LINE signature check (even in tests — use the same code path).
- ⛔ Use `print()` for logging in backend.
- ⛔ Inject raw LINE messages into AI prompts (prompt-injection vector).
- ⛔ Add a real `*_real.py` adapter that holds hardcoded URLs or keys.
- ⛔ Cache or store user-uploaded images outside `backend/var/uploads/`
  (mock) or Supabase Storage (real).
- ⛔ Remove a test to make CI green. If a test fails, fix the code or
  update the test with a written reason.
- ⛔ Skip the `## Test Plan` updates when adding a new scenario.

---

## Acceptance Criteria

The feature is **done** when **all 12** are true:

1. **AC-01 — One-command bootstrap.** A fresh `git clone` followed by
   the `Setup` commands above boots both apps with **zero network access
   to Supabase, LINE, or Anthropic.** All requests served by mocks.
2. **AC-02 — Health gate.** `GET /health` returns 200 + `{"status":"ok"}`.
   The frontend's `/api/health` route does the same.
3. **AC-03 — Auth works three ways.**
   - Email/password signup + login (Supabase Auth, mock mode).
   - LIFF login stub: a button on `/login` calls the backend mock
     and creates a session for a fake LINE user.
   - Bcrypt-hashed passwords; JWT issued and verified by FastAPI.
4. **AC-04 — Property CRUD.** Authenticated agent can create, list,
   update, archive a `properties` row with at minimum: title,
   property_type, price, size_sqm, district, province, near_bts_mrt,
   bedrooms, bathrooms, images (URLs).
5. **AC-05 — AI listing generator.** `POST /api/generate-listing` with
   property fields returns a JSON body with `title`, `description`,
   `hashtags`, `seo_keywords`, `platform` for each of
   `["ddproperty", "livinginsider", "facebook", "general"]`.
   Mock AI returns deterministic Thai text keyed on property features.
   Latency ≤ 2 s in mock mode.
6. **AC-06 — Generated listing persistence.** A created listing is
   saved to `generated_listings`, retrievable by `property_id`, editable
   in the UI, and re-saves without losing prior versions.
7. **AC-07 — LINE webhook signature.** `POST /webhook/line` with
   `X-Line-Signature` that matches HMAC-SHA256 of the raw body with the
   configured channel secret → 200. Mismatched signature → 401, no DB write.
8. **AC-08 — LINE webhook side effects.** A verified inbound `text`
   event from a new LINE user creates a `Lead` (source=`line`,
   line_user_id set) + a `Message` (`direction='inbound'`,
   `raw_data` = full event). Subsequent messages from the same
   `line_user_id` reuse the same lead. Duplicate `event_id`s are ignored.
9. **AC-09 — Dashboard.** `GET /api/dashboard` returns the last 20
   inbound messages, last 5 properties, and a counter of new leads.
   The frontend `/dashboard` page renders all three.
10. **AC-10 — Image upload.** `POST /api/upload-image` accepts a
    multipart file, returns a public URL backed by `backend/var/uploads/`
    in mock mode. The frontend form includes a real working uploader.
11. **AC-11 — Tests green.** Backend: `pytest -q` passes, coverage ≥80 %.
    Frontend: `npm test` passes with at least 1 unit test per page +
    one happy-path Playwright spec.
12. **AC-12 — Real-adapter swap.** With `USE_MOCKS=false` and valid
    `SUPABASE_URL` + `ANTHROPIC_API_KEY` + `LINE_CHANNEL_*` envs in
    `.env`, the same backend restarts and runs against real services
    without code changes. (Real-adapter network tests are skipped by
    default in CI.)

---

## Test Plan (ST-NNN scenarios)

Each scenario is referenced by at least one task in the plan.

| ID        | Title                                                                  | Covers AC |
|-----------|------------------------------------------------------------------------|-----------|
| **ST-001**| `GET /health` returns 200 + `{"status":"ok"}`                          | AC-02     |
| **ST-002**| Signup with email/password → 200; duplicate email → 409                | AC-03     |
| **ST-003**| Login with correct password → JWT; wrong password → 401                | AC-03     |
| **ST-004**| LIFF login stub → session for fake LINE user                           | AC-03     |
| **ST-005**| Create / list / update / archive a property (auth required)            | AC-04     |
| **ST-006**| Generate listing for a condo with photos → all 4 platforms, Thai text  | AC-05     |
| **ST-007**| Generate listing for a house (no BTS), small land size                 | AC-05     |
| **ST-008**| Save generated listing → retrievable by property_id, editable         | AC-06     |
| **ST-009**| LINE webhook valid signature → 200, lead + message created             | AC-07/AC-08 |
| **ST-010**| LINE webhook bad signature → 401, zero DB writes                       | AC-07     |
| **ST-011**| LINE webhook replay (same event_id) → ignored                          | AC-08     |
| **ST-012**| Two messages from same `line_user_id` → one lead, two messages        | AC-08     |
| **ST-013**| `GET /api/dashboard` returns last-20 messages + last-5 properties      | AC-09     |
| **ST-014**| Frontend `/dashboard` renders the three sections                       | AC-09     |
| **ST-015**| `POST /api/upload-image` returns a URL pointing into `var/uploads/`    | AC-10     |
| **ST-016**| Frontend property form accepts an uploaded image & renders preview     | AC-10     |
| **ST-017**| Vitest unit tests for `lib/api.ts` and `PropertyForm.tsx`              | AC-11     |
| **ST-018**| Playwright happy-path: signup → add property → AI gen → save          | AC-11     |
| **ST-019**| Real-adapter swap test (skipped unless env flag) — Anthropic real client hits test server | AC-12 |
| **ST-020**| Mock adapter snapshot — mock responses are stable across reruns        | AC-12     |

---

## Out of Scope (Month 1)

These are explicitly **not** in this AIDLC cycle. Listing them so
later cycles (Month 2+) pick them up deliberately.

- **Real Supabase project, real LINE OA, real Anthropic billing.** The
  MVP runs fully mocked; the real adapters ship with code but require
  external accounts to exercise.
- **Multi-agent teams.** `teams` table exists but RLS stays
  single-tenant (user-scoping only).
- **Payments / billing / quotas.**
- **WebSockets for real-time messaging.** Dashboard polls every 5 s
  in MVP; Socket.IO / SSE is a v2 concern.
- **Auto-posting to DDProperty, Livinginsider, Facebook.** Output is
  copy-pasteable text only; no scraping/posting bot.
- **Image vision analysis.** The mock AI accepts captions; the real
  AI's image-features path is stubbed (returns empty list).
- **Contract generation, e-signature, PDF export.**
- **Google Calendar two-way sync.**
- **CRM analytics (conversion funnels, revenue dashboards).**
- **Mobile app, native LINE Flex Messages.** JSON-only replies.
- **Audit log UI.** `audit_logs` table created; no reader page.
- **i18n beyond Thai + English keys.** UI is Thai-first; English
  fallback strings; no runtime locale switcher.
- **Production-grade observability.** Sentry, Logtail, OpenTelemetry —
  integration points wired but not enabled.

---

## Open Questions

> User answered all Q1–Q7 already. Below are residual questions the
> plan phase should pin down; defaults are my recommendation.

- **OQ-A — Auth provider split.** LIFF + email or LIFF-only for MVP?
  **Default:** both, with a toggle. (LIFF-only is cleaner but blocks
  non-LINE-savvy agents.)
- **OQ-B — Image uploads in mock mode — disk or in-memory?**
  **Default:** disk under `backend/var/uploads/`, served via a
  dedicated FastAPI static route. Lets the Playwright spec grab the
  URL and assert HTTP 200.
- **OQ-C — Mock AI idempotency.** Should the mock AI return a fixed
  Thai string or hash the inputs and template in?
  **Default:** templated with `{property_type}` + `{district}` etc., so
  the Playwright test can assert on substring "คอนโด" for condos.
- **OQ-D — DB migration runner.** Should the mock DB auto-apply
  `migrations/*.sql` on startup, or require a separate `migrate` CLI?
  **Default:** auto-apply on startup (mock only); real path uses
  Supabase SQL editor / `supabase db push`.
- **OQ-E — Test database isolation.** Single in-memory mock DB shared
  across tests, or per-test fixture that re-runs migrations?
  **Default:** per-test function-scoped fixture (resets between tests
  but reuses migration cache → fast).
- **OQ-F — AI fallback policy.** When Anthropic is configured but
  errors, do we silently fall back to Gemini, or surface the error?
  **Default:** silent fallback on `429` / `5xx` / `TimeoutException`,
  error surfaced on `4xx` (other than 429).

---

_Updated: 2026-07-03T06:25:00Z — specifying phase ready for review._
