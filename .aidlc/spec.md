# Spec: Cycle 2 — Real Adapter Wiring

> **Status:** specifying → ready for plan
> **Branch:** `feat/real-adapter-wiring`
> **Source brief:** the spec's "Out of Scope (Month 1)" + `docs/adapters.md`
> "Per-adapter status" table.
> **Plan:** [`.aidlc/plan.md`](./plan.md) (T-101…T-105)

---

## Objective

Replace the four `NotImplementedError` skeletons in `app/adapters/*/real.py`
with real implementations so the same backend restarts against real
Supabase + LINE + Anthropic + Supabase Storage by flipping
`USE_MOCKS=false` — **zero router code changes**.

The mocks remain in place; the boundary is stable. What changes is that
the real adapters actually do something.

**Who the user is:** a deployer setting up the SaaS for a single Thai
real estate agent in production. They obtain Supabase / LINE / Anthropic
credentials, set env flags, deploy.

**Success = a fresh `git clone` + `USE_MOCKS=false` + valid envs, the
backend restarts and:**
- Signups create real rows in Supabase Postgres
- LINE webhooks still verify + persist; outbound replies hit the real
  Reply API
- AI listing generation calls real Anthropic Claude 3.5 Sonnet
- Image uploads land in Supabase Storage; URLs serve the bytes

…with all the same test scenarios (ST-001…ST-020) still passing against
mocks (CI green) and a new smoke-test suite passing against the real
services (`RUN_LIVE_SMOKE=1`, dev project, manual workflow_dispatch).

---

## Acceptance criteria

1. **AC-RW-01 — Real Supabase adapter** implements all 16 Protocol
   methods with PostgREST calls + per-user scoping.
2. **AC-RW-02 — Real LINE adapter** implements `send_reply()` against
   the real Reply API + bot-user-id self-message filter + Markdown
   stripper + 5/4500 chunker.
3. **AC-RW-03 — Real AI adapter (Anthropic)** calls Claude 3.5 Sonnet
   via the `anthropic` SDK; falls back to Gemini on 429/5xx/timeout;
   surfaces 4xx errors.
4. **AC-RW-04 — Real Storage adapter** uploads to Supabase Storage and
   returns a public/signed URL.
5. **AC-RW-05 — CI stays green** — `pytest --cov=app --cov-fail-under=80`
   still passes; real-adapter tests use `httpx.MockTransport` and run
   without network.
6. **AC-RW-06 — Live smoke tests** — `RUN_LIVE_SMOKE=1` runs against a
   real dev project via `workflow_dispatch`; skipped in normal CI.
7. **AC-RW-07 — Docs updated** — `docs/adapters.md` "Per-adapter status"
   table shows "Real wiring shipped" for all four. `docs/runbook.md`
   has a "Bring up real services" section.
8. **AC-RW-08 — Router code unchanged** — `git diff` on
   `app/routers/*.py` is empty (or only typing fixes); only
   `app/adapters/**/real.py` and tests change.

---

## Commands

All commands run from the repo root unless noted.

### Real-mode local dev (after T-105 lands)

```bash
# .env (real)
USE_MOCKS=false
SUPABASE_URL=https://abc.supabase.co
SUPABASE_ANON_KEY=eyJ...
LINE_CHANNEL_SECRET=...
LINE_CHANNEL_ACCESS_TOKEN=...
ANTHROPIC_API_KEY=sk-...

# Boot
cd backend && source venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Smoke (mock-mode: still works; flip flag for real)
pytest -q
```

### Run live smoke tests

```bash
# One-off: against your dev project
RUN_LIVE_SMOKE=1 \
  SUPABASE_URL=... SUPABASE_ANON_KEY=... \
  LINE_CHANNEL_SECRET=... LINE_CHANNEL_ACCESS_TOKEN=... \
  ANTHROPIC_API_KEY=... \
  pytest -q tests/test_live_smoke.py
```

Or via GitHub Actions: Actions → "CI" → "Run workflow" → check
"Run live smoke tests". This uses GitHub Actions secrets.

### Quality gates (unchanged from Month 1)

```bash
cd backend && source venv/bin/activate
ruff check app/ tests/
ruff format --check app/ tests/
mypy app/
pytest -q --cov=app --cov-fail-under=80

cd ../web
npm run lint && npm run typecheck && npm test
```

---

## Project Structure (additions only)

```
backend/app/adapters/
├── supabase/
│   └── real.py             ← REPLACES skeleton (T-101)
│   └── real_auth.py        ← NEW (T-101b: Supabase Auth helpers)
├── line/
│   ├── real.py             ← REPLACES skeleton (T-102)
│   ├── bot_info.py         ← NEW (T-102: GET /v2/bot/info w/ cache)
│   └── transforms.py       ← NEW (T-102: Markdown strip + chunker
│                              promoted from PR #2)
├── ai/
│   ├── anthropic_real.py   ← REPLACES skeleton (T-103)
│   ├── anthropic_real_client.py  ← NEW (T-103: SDK wrapper w/ retries)
│   └── prompts.py          ← NEW (T-103: versioned prompt templates)
└── storage/
    └── supabase_real.py    ← REPLACES skeleton (T-104)

backend/tests/
├── adapters/
│   ├── test_real_supabase.py   ← NEW (T-101)
│   ├── test_real_line.py       ← NEW (T-102)
│   ├── test_real_ai.py         ← NEW (T-103)
│   └── test_real_storage.py    ← NEW (T-104)
└── test_live_smoke.py          ← NEW (T-105: RUN_LIVE_SMOKE=1 only)

.github/workflows/ci.yml   ← UPDATED (T-105: workflow_dispatch live smoke)

docs/
├── adapters.md             ← UPDATED (T-105: shipping status)
├── runbook.md              ← UPDATED (T-105: "Bring up real services")
└── (new) production-deploy.md   ← NEW (T-105: deploy walk-through)
```

---

## Code Style (unchanged from Month 1)

- `from __future__ import annotations` everywhere.
- Type hints on every public function; `-> dict[str, str]` not `dict`.
- Pydantic v2 models for every DTO. Use `ConfigDict(extra="forbid")`.
- Logging: `get_logger(__name__)`, never `print()`.
- Errors: raise typed domain exceptions; map to HTTP in
  `app/main.py::register_exception_handlers`.
- All real-adapter network calls go through `httpx.AsyncClient` with
  explicit timeouts (`timeout=httpx.Timeout(10.0, connect=5.0)`).
- Real adapter methods MUST raise the same Protocol types (no extra
  exceptions that bypass the router's error handlers).

---

## Testing Strategy

| Layer | Tooling | What it covers | Where it lives |
|-------|---------|----------------|----------------|
| Real adapter unit | pytest + httpx.MockTransport | All real adapter methods, no network | `backend/tests/adapters/test_real_*.py` |
| Live smoke | pytest + real dev project | End-to-end against real services | `backend/tests/test_live_smoke.py` (RUN_LIVE_SMOKE=1) |
| Mock parity | pytest (unchanged) | Mocks still satisfy Protocol | `backend/tests/adapters/test_mock_*.py` |
| Real-swap Protocol | pytest (unchanged from T-012) | Real adapter shape matches Protocol | `backend/tests/test_real_swap.py` |

**Coverage target:** ≥ 80 % lines for `app/`. Real adapters
(`app/adapters/*_real.py`) are excluded from coverage as before, per
`pyproject.toml` `[tool.coverage.run] omit = ["app/adapters/*_real.py"]`.
The new `test_real_*.py` tests run in CI without network.

**CI strategy:**
- `pytest` (default) — runs all mock + Protocol tests, skipped live smoke
- `pytest` with `RUN_LIVE_SMOKE=1` — manual workflow_dispatch only
- `workflow_dispatch` job uses GitHub Actions secrets for real creds

---

## Boundaries (in-scoped rules)

### Always do

- ✅ Run `ruff check + mypy + pytest` before committing.
- ✅ Use `httpx.MockTransport` for real-adapter tests; no live network in CI.
- ✅ Type-narrow real-adapter return values explicitly.
- ✅ Cap request timeouts (`httpx.Timeout(10.0, connect=5.0)`).
- ✅ Document any new env vars in `.env.example` + `docs/runbook.md`.
- ✅ Keep router code unchanged (AC-RW-08).

### Ask first

- 🟡 Adding a new top-level dependency.
- 🟡 Changing the Protocol surface (would require router changes).
- 🟡 Adding a third AI provider beyond Anthropic + Gemini.
- 🟡 Modifying the Supabase migrations.

### Never do

- ⛔ Hit real APIs in regular CI.
- ⛔ Commit secrets, real tokens, or `.env` files.
- ⛔ Bypass the signature check in tests (use the same code path).
- ⛔ Cache real LLM responses across test runs (would invalidate smoke).
- ⛔ Remove a test to make CI green.
- ⛔ Modify `app/routers/*` to accommodate a real adapter quirk.

---

## Out of Scope (Cycle 2)

These remain out of scope after this cycle ships. Listing them so
Cycle 3+ can pick them up deliberately.

- **Multi-tenant teams / RLS policies.** Single-tenant user-scoping only.
- **WebSockets / real-time push.** Dashboard still polls.
- **Image vision (Claude Vision API).** Text-only prompts.
- **Auto-posting to DDProperty / Livinginsider / Facebook.**
- **Payments / billing / quotas.**
- **Contract generation / e-signature / PDF export.**
- **Google Calendar two-way sync.**
- **CRM analytics (conversion funnels, revenue dashboards).**
- **Mobile app, native LINE Flex Messages.**
- **Audit log UI.**
- **i18n beyond Thai + English keys.**
- **Production-grade observability.** Sentry, Logtail, OpenTelemetry.

---

## Open Questions

> All resolved with documented defaults.

- **OQ-RW-A — Live smoke test environment.** Use a dedicated dev
  Supabase project + LINE sandbox channel + Anthropic eval-tier key?
  **Default:** yes, all three. GitHub Actions secrets hold the creds.
  Manual `workflow_dispatch` only. **Cost estimate:** ~$0.05 per run on
  Anthropic eval tier; free on Supabase free tier + LINE sandbox.
- **OQ-RW-B — Anthropic vs Gemini default.** Which is the primary
  adapter when both are configured? **Default:** Anthropic
  (Claude 3.5 Sonnet), with Gemini as silent fallback per OQ-F.
  Configurable via `AI_PROVIDER` env (already in place from Month 1).
- **OQ-RW-C — Supabase Auth integration.** Should the backend issue
  its own JWT (current) or use Supabase's JWT directly?
  **Default:** keep current pattern (FastAPI-issued JWT). Supabase
  Auth helper is for the real `signup` flow (Supabase `signUp` API →
  server-side create the matching `users` row).
- **OQ-RW-D — Image bucket privacy.** Public bucket (readable via URL
  without auth) or private (signed URLs)? **Default:** public bucket
  for simplicity; switch to signed URLs if Supabase project requires
  private storage.

---

_Updated: 2026-07-03T22:30:00Z — spec ready, plan in `.aidlc/plan.md`._
