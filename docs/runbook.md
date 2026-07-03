# Runbook

Day-2 operations playbook for the Real Estate AI Agent MVP.

## Local development

```bash
# Backend (Python 3.11)
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # default uses mocks; no keys needed
pytest                 # ~136 tests, runs offline
uvicorn app.main:app --reload --port 8000

# Frontend (Next.js)
cd web
npm install
cp .env.example .env.local
npm test                # vitest
npm run dev             # http://localhost:3000
```

Open `http://localhost:3000`, click **Sign up**, fill in the form. Use
**Log in with LINE** to test the LIFF stub. Toggle `USE_MOCKS=true` in `.env` for
the all-mocks dev mode.

## Where things live

| Need to change …            | File(s)                                       |
|-----------------------------|-----------------------------------------------|
| A property/location field   | `backend/app/domain/property.py` + `web/lib/types.ts` + `PropertyForm.tsx` |
| A new endpoint              | `backend/app/routers/<name>.py` + `main.py` + `tests/test_<name>.py` |
| A new DB table              | `backend/migrations/<NNN>_<name>.sql` + `app/adapters/supabase/_schema.py` + run the SQL against the real Supabase project |
| Adapter swap (mock → real)  | env flag in `.env` — see `adapters.md` |
| AI prompt                   | `backend/app/adapters/ai/<provider>_mock.py` |
| LINE handler                | `backend/app/services/lead_pipeline.py` |
| Frontend page layout        | `web/app/(app)/<page>/page.tsx` |
| Frontend API wrapper        | `web/lib/<domain>.ts` |
| AIDLC state / progress      | `.aidlc/state.md` + `.aidlc/plan.md` |

## Adding a new feature (the AIDLC loop)

1. Update `.aidlc/state.md` notes (mark previous task done, set next).
2. Branch: `feat/<feature-name>` (already `feat/month-1-mvp` for this MVP).
3. Implement: vertical slice (DB → service → router → frontend page → tests).
4. Verify:
   - `cd backend && source .venv/bin/activate && pytest`
   - `cd web && npm test && npm run build`
5. Update CHANGELOG (this MVP is too early for a formal one — keep notes in `.aidlc/state.md`).
6. Push, open PR.

## Debugging

### "Why is my LINE webhook returning 503?"

```bash
# Tail the server logs while sending an event
tail -f /tmp/uvicorn.log

# Send a signed event manually
python3 -c "
import json, hmac, hashlib, base64, urllib.request
SECRET = 'dev-line-channel-secret-change-me'
body = json.dumps({'events':[{'type':'message','event_id':'1','source':{'userId':'U'}}]}).encode()
sig = base64.b64encode(hmac.new(SECRET.encode(), body, hashlib.sha256).digest()).decode()
r = urllib.request.Request('http://127.0.0.1:8000/webhook/line', data=body,
    headers={'X-Line-Signature': sig, 'Content-Type':'application/json'}, method='POST')
print(urllib.request.urlopen(r).read())
"
```

The handler returns:
- 401 — signature missing / wrong. Check `LINE_CHANNEL_SECRET` in `.env`.
- 503 — events arrived but no agent found. Set `LINE_DEFAULT_AGENT_ID` or have
  at least one user signed up.
- 400 — JSON parse failed AFTER signature verified. The body is bad.

### "Why is my backend test failing on email duplicates?"

The mock Supabase singleton is process-global. Two tests using the same
email will see the 409 from the second test onward. The fix is to use
`reset_mock_singleton()` in an `autouse=True` fixture — see
`tests/test_storage.py`.

### "Why are my listings empty?"

Check:
1. Are images uploading? Look for `var/uploads/{key}.png` on disk after a
   POST `/api/upload-image`.
2. Did the AI adapter run? Look for `ai_model` field on the response —
   if it says `claude-3-5-sonnet-mock` you're in mock mode.
3. Is the property saved? Check `/api/properties` — the form redirects to
   `/properties/{id}` only after the insert succeeds.

### "Why is the dashboard stuck on 0?"

The dashboard polls every 5 s. If `new_leads_count` is 0 even after webhook
events, check:
- `LINE_DEFAULT_AGENT_ID` vs. logged-in user.
- Status of the lead row: `db.query("leads", filters={"user_id": user_id})`
  should match what the dashboard counts.

## Production rollout

When the project goes from "mock everywhere" to "real Supabase + real
LINE OA + real Anthropic":

1. **Provision real services** (Supabase project, LINE OA, Anthropic API key).
2. **Apply migrations** to the real Supabase DB:
   ```bash
   psql "$SUPABASE_URL" -f backend/migrations/001_init.sql
   ```
   (Or use the Supabase dashboard SQL editor.)
3. **Fill in `.env`** for production with the real keys (see
   `docs/adapters.md` for the matrix).
4. **Set `USE_MOCKS=false`** (or flip each `USE_REAL_*` individually).
5. **Smoke-test the webhook** with a real LINE account messaging the OA.
6. **Set `LINE_DEFAULT_AGENT_ID`** to the agent user that owns the OA.

## Coverage gate

`backend/pyproject.toml` enforces `pytest --cov-fail-under=80`. Current
coverage is **94%** on `app/`. Real-stubs (`*_real.py`) sit at ~70% by
design — their methods raise `NotImplementedError` until wired.

## Incident on-call

| Symptom                                | First check                                |
|----------------------------------------|--------------------------------------------|
| Webhook returns 401                    | `LINE_CHANNEL_SECRET` rotation; verify signature with `tests/test_line_webhook.py` |
| /api/properties returns 500            | `get_db()` singleton out of sync; restart |
| Generated listings are repetitive     | Add new templates in `_mock.py` matching property_type+platform |
| Frontend build fails with type error  | `npm run typecheck` → fix; check `lib/types.ts` mirrors backend DTOs |
| AI responses rate-limited              | Wait; the fallback chain handles it transparently |
