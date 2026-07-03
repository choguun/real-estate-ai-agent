# Real Estate AI Agent (Thailand) 🇹🇭

> A LINE-integrated SaaS that helps Thai real estate agents generate polished
> property listings with AI and manage leads from one dashboard.

## Status

🏁 **Month-1 MVP — shipped.** All 12 AIDLC tasks done. Spec, plan, state in
[`.aidlc/`](./.aidlc/). See [`docs/`](./docs/) for the day-2 operations
playbook.

## Quick start

```bash
# Backend
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # mocks-first: no API keys needed
pytest                     # ~136 tests pass; coverage gate 80% enforced
uvicorn app.main:app --reload --port 8000

# Frontend
cd web && npm install
cp .env.example .env.local
npm test                   # vitest — 36 tests
npm run dev                # http://localhost:3000
```

Sign up at `/signup`, log in at `/login`, create a property at
`/properties/new` with photos, and try **✨ Generate** to draft Thai copy for
DDProperty / Livinginsider / Facebook / General.

## Architecture

Two services (Next.js + FastAPI) plus a four-pair adapter layer for Supabase,
AI, LINE, and Storage. Mocks-first by default; flip env flags to swap in real
services — see [`docs/adapters.md`](./docs/adapters.md).

```
[Agent] ─► web (Next.js) ─► backend (FastAPI) ─► adapters ─► Supabase / AI / LINE / Storage
                                       ▲
                                       │ HMAC-SHA256 verified webhook
                                       │
                                  [LINE Cloud]
```

Full architectural diagrams and request lifecycles in
[`docs/architecture.md`](./docs/architecture.md).

## Documentation

| Doc                                                  | Purpose                                       |
|------------------------------------------------------|-----------------------------------------------|
| [`.aidlc/spec.md`](./.aidlc/spec.md)                 | What we're building — AC-01…AC-12, ST-001…ST-020 |
| [`.aidlc/plan.md`](./.aidlc/plan.md)                 | The 12 vertical slices T-001…T-012             |
| [`.aidlc/state.md`](./.aidlc/state.md)               | Where we are right now                         |
| [`docs/architecture.md`](./docs/architecture.md)     | Layers, request lifecycles, what *isn't* here  |
| [`docs/adapters.md`](./docs/adapters.md)             | The 4 adapter pairs + when each is used        |
| [`docs/runbook.md`](./docs/runbook.md)               | Debugging & day-2 operations                  |

## Tech stack

| Layer       | Tech                                                          |
|-------------|---------------------------------------------------------------|
| Frontend    | Next.js 15 · React 19 · Tailwind · vitest · Playwright         |
| Backend     | FastAPI · Pydantic v2 · Uvicorn · pytest · ruff · mypy          |
| Database    | Supabase Postgres + Auth + Storage (mocked locally)            |
| Messaging   | LINE Messaging API + LIFF + webhook HMAC-SHA256 (mocked locally) |
| AI          | Anthropic Claude 3.5 Sonnet + Google Gemini 2.0 (mocked locally) |
| Deploy      | Vercel (web) · Railway (backend); runbook + rollout checklist in `docs/runbook.md` |

## CI

`.github/workflows/ci.yml` runs ruff + mypy + pytest on the backend, plus
lint + typecheck + vitest on the frontend. Backend coverage gate is enforced
at 80%.

End-to-end Playwright tests live in `web/tests/e2e/happy-path.spec.ts`. They
require both servers running locally (see `playwright.config.ts`); CI support
needs browser binaries — `npx playwright install chromium` once.

## License

UNLICENSED — proprietary. See [`LICENSE`](./LICENSE).
