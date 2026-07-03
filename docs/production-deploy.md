# Production Deploy

End-to-end guide to deploying the Real Estate AI Agent (Thailand) MVP to
production with REAL Supabase + LINE + Anthropic services. The mock-first
dev loop stays intact — the same backend restarts against real services
by flipping env flags.

## TL;DR

```bash
# 1. Create a Supabase project + LINE OA + Anthropic account (see below)
# 2. Set env flags in your deploy target (Vercel + Railway)
# 3. Push to deploy. No code changes.
```

## What you need before deploying

| Service | What to create | Where | Cost |
|---------|----------------|-------|------|
| Supabase project | Free tier works for MVP | [supabase.com](https://supabase.com) | $0 up to 500 MB / 50k rows |
| LINE Official Account | Messaging API channel | [developers.line.biz](https://developers.line.biz) | $0 (free tier 500 messages/mo) |
| Anthropic API key | Claude 3.5 Sonnet access | [console.anthropic.com](https://console.anthropic.com) | ~$3 / 1M input tokens |
| Vercel (frontend) | Hobby plan | [vercel.com](https://vercel.com) | $0 |
| Railway (backend) | Hobby plan | [railway.app](https://railway.app) | $5/mo flat |

## Step 1 — Supabase setup

1. Create a new project at https://app.supabase.com.
2. SQL editor → paste `backend/migrations/001_init.sql` → Run.
3. Settings → API:
   - Copy `Project URL` → `SUPABASE_URL`
   - Copy `anon public` key → `SUPABASE_ANON_KEY`
   - Copy `service_role` key → `SUPABASE_SERVICE_ROLE_KEY`
4. Storage → Create bucket `uploads` (public for MVP; switch to private
   + signed URLs by setting `SUPABASE_STORAGE_PRIVATE=true`).
5. (Optional) Auth → Users → disable email confirmation for dev.

## Step 2 — LINE OA setup

1. Create a LINE Official Account at https://manager.line.biz.
2. LINE Developers Console → create a Messaging API channel.
3. Channel settings:
   - Copy `Channel secret` → `LINE_CHANNEL_SECRET`
   - Copy `Channel access token` (long-lived) → `LINE_CHANNEL_ACCESS_TOKEN`
4. Webhook URL → point at your backend:
   - `https://<your-railway-app>.up.railway.app/webhook/line`
   - Toggle "Use webhook" ON
   - Verify (LINE shows "Success" when our /webhook/line returns 200)
5. Auto-reply messages → DISABLE (so our backend handles every event).

## Step 3 — Anthropic API key

1. https://console.anthropic.com → API Keys → Create Key
2. Copy → `ANTHROPIC_API_KEY`
3. (Optional) Add `ANTHROPIC_MODEL=claude-3-5-sonnet-latest` to override
   the default.

## Step 4 — Backend env (Railway)

In Railway → your service → Variables:

```bash
# Master switch — turn OFF for real services
USE_MOCKS=false

# Real Supabase
USE_REAL_SUPABASE=true
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_ANON_KEY=<from step 1>
SUPABASE_SERVICE_ROLE_KEY=<from step 1>

# Real LINE
USE_REAL_LINE=true
LINE_CHANNEL_SECRET=<from step 2>
LINE_CHANNEL_ACCESS_TOKEN=<from step 2>

# Real AI
USE_REAL_AI=true
ANTHROPIC_API_KEY=<from step 3>
ANTHROPIC_MODEL=claude-3-5-sonnet-latest

# Storage
SUPABASE_STORAGE_BUCKET=uploads
SUPABASE_STORAGE_PRIVATE=false

# Auth
JWT_SECRET=<openssl rand -hex 32>
JWT_ALGORITHM=HS256
JWT_TTL_SECONDS=86400
```

## Step 5 — Frontend env (Vercel)

In Vercel → your project → Settings → Environment Variables:

```bash
BACKEND_URL=https://<your-railway-app>.up.railway.app
NEXT_PUBLIC_API_URL=https://<your-railway-app>.up.railway.app
```

## Step 6 — Deploy

```bash
# Backend
cd backend
railway up

# Frontend
cd ../web
vercel --prod
```

## Step 7 — Verify

### Smoke test the deployed backend

```bash
# Health
curl https://<your-railway-app>.up.railway.app/health
# → {"status":"ok"}

# Sign up
curl -X POST https://<your-railway-app>.up.railway.app/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"smoke@example.com","password":"supersecret123","full_name":"Smoke"}'
# → {"access_token":"...","token_type":"bearer","user":{...}}

# Add a property (use the token from above)
TOKEN="<paste access_token>"
curl -X POST https://<your-railway-app>.up.railway.app/api/properties \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"title":"คอนโดทดสอบ","property_type":"condo","price":3500000,"district":"วัฒนา"}'
# → {"id":"...","title":"คอนโดทดสอบ",...}

# Generate a listing
PID="<paste property id>"
curl -X POST https://<your-railway-app>.up.railway.app/api/generate-listing \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d "{\"property_id\":\"$PID\"}"
# → {"property_id":"...","variants":[{...4 platforms}]}
```

### Smoke test the LINE webhook

```bash
# Sign a payload with the real channel secret
python3 -c "
import base64, hmac, hashlib, json
secret = b'<LINE_CHANNEL_SECRET>'
body = json.dumps({'events': [{
    'type': 'message', 'webhookEventId': 'evt-smoke-001',
    'source': {'userId': 'U-smoke-1', 'type': 'user'},
    'message': {'type': 'text', 'text': 'Hello from smoke test'}
}]}).encode()
sig = base64.b64encode(hmac.new(secret, body, hashlib.sha256).digest()).decode()
print('X-Line-Signature:', sig)
print('Body:', body.decode())
"
# Then POST that body + signature to your webhook URL
```

A successful run: 200, a new Lead appears in your Supabase `leads` table,
and a new row in `messages` with `direction='inbound'`.

## Step 8 — Run live smoke tests in CI

GitHub → Actions → CI → Run workflow → check "Run live smoke tests".

The workflow uses the following secrets (Settings → Secrets → Actions):

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `LINE_CHANNEL_SECRET`
- `LINE_CHANNEL_ACCESS_TOKEN`
- `ANTHROPIC_API_KEY`

These stay encrypted and only used by the `live-smoke` job (which only
runs on `workflow_dispatch` or `main` branch).

## Rollback

The `USE_MOCKS=true` master switch flips everything back to in-process
mocks. To roll back:

1. Set `USE_MOCKS=true` on Railway
2. Redeploy
3. Optionally: `USE_REAL_LINE=false` (etc.) to flip one at a time

The mock DB is in-process — data inserted during the mock phase is lost
on restart. Real data in Supabase is untouched.

## Cost estimate (1k users / 100 listings / 10k LINE messages)

| Service | Usage | Cost |
|---------|-------|------|
| Vercel | Hobby | $0 |
| Railway | Hobby | $5/mo |
| Supabase | 500 MB + 50k rows | $0 |
| LINE | 15k messages (free tier is 500) | $0–$15 |
| Anthropic | ~3M tokens (Sonnet) for 10k listings | ~$30 |
| **Total** | | **~$50 / month** |

## What's NOT in production yet

These are Cycle 3+ candidates (see spec.md "Out of Scope"):

- Multi-tenant teams / RLS policies
- WebSockets for real-time messaging
- Image vision (Claude Vision API)
- Auto-posting to DDProperty / Livinginsider / Facebook
- Payments / billing
- Audit log UI
- Sentry / OpenTelemetry
- i18n beyond Thai + English keys
- Mobile app
- Google Calendar two-way sync
- CRM analytics
- Contract generation / e-signature / PDF export
