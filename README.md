# Real Estate AI Agent (Thailand) 🇹🇭

> A LINE-integrated SaaS that helps Thai real estate agents generate polished
> property listings with AI and manage leads from one dashboard.

## Status

🚧 **Month 1 MVP — in development.** See [`PLAN.md`](./PLAN.md) for the
4-week roadmap and [`DB.md`](./DB.md) for the database schema.

The active development cycle is tracked in [`.aidlc/state.md`](./.aidlc/state.md).
The full spec lives at [`.aidlc/spec.md`](./.aidlc/spec.md), and the ordered
task list at [`.aidlc/plan.md`](./.aidlc/plan.md).

## Stack

| Layer       | Tech                                                          |
|-------------|---------------------------------------------------------------|
| Frontend    | Next.js 15 (App Router) · Tailwind · shadcn/ui · LIFF SDK     |
| Backend     | FastAPI · Pydantic v2 · Uvicorn                               |
| Database    | Supabase Postgres + Auth + Storage                            |
| Messaging   | LINE Messaging API + LIFF (login)                             |
| AI          | Anthropic Claude 3.5 Sonnet (fallback: Google Gemini 2.0)     |
| Deploy      | Vercel (frontend) · Railway (backend)                         |

## Development

All external integrations run against **mocks** by default (no real API keys
needed for local dev). Real adapters activate automatically when the
appropriate `USE_<X>=false` env flags are set.

```bash
# Frontend
cd web
npm install
npm run dev

# Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

See `.env.example` in each package for the full configuration surface.

## License

UNLICENSED — proprietary.
