# LINE integration — Gap analysis vs. NousResearch/hermes-agent#23197

**Date:** 2026-07-03
**Source:** [`NousResearch/hermes-agent#23197`](https://github.com/NousResearch/hermes-agent/pull/23197) (MERGED, 1638 LOC adapter, 73 tests, plugin-form)
**Scope of the comparison:** what their `LineAdapter` does for a generic chat platform that we don't do (or don't yet do) for the Thai real-estate AI agent MVP.

This is an analysis only — **not a plan to copy their adapter wholesale.** They run aiohttp and serve as a Hermes Agent platform plugin; we're a FastAPI monolith with mocks-first adapters. Architectural mismatch means most of their work does not transfer directly.

The value of looking is to find the **real gaps** in our `backend/app/adapters/line/*` + `routers/line_webhook.py` + `services/lead_pipeline.py` that are independently worth fixing because they affect security, correctness, or operability.

---

## TL;DR — what would actually move the needle for us

| # | Gap | Effort | Verdict |
|---|---|---|---|
| 1 | Body-size cap on webhook payload | XS (3 lines) | **Fix now** |
| 2 | Self-message filter (ignore our own outbound echoes) | XS | **Fix now** |
| 3 | Reply-token cache + Push fallback on outbound | S | **Fix now** |
| 4 | Markdown stripping + 5-message / 4500-char chunking on outbound text | S | **Fix now** |
| 5 | `unsend` event handling (mark inbound message as withdrawn) | XS | **Defer** (1-migration scope; not in this PR) |
| 6 | Image / audio / video / file / sticker / location inbound parsing | M | Defer (not in MVP scope) |
| 7 | Image / audio / video SEND with media-token HTTPS serving + `LINE_PUBLIC_URL` | M-L | Defer until media send is needed |
| 8 | Three-allowlist (`LINE_ALLOWED_USERS` / `_GROUPS` / `_ROOMS`) gating | XS | Defer (single-tenant MVP) |
| 9 | Slow-LLM postback button (`replyToken` + 60s TTL → Template Buttons) | M | **Skip** (we don't run an async LLM yet) |
| 10 | Loading indicator (`POST /message/loading`) | XS | Defer (UX polish) |
| 11 | `things` / `accountLink` / `memberJoined` events | XS | Defer (we don't run IoT or LIFF account linking) |

What's actually worth pulling in: **#1, #2, #3, #4, #5.**

Everything else is either N/A for our use case (the slow-LLM button is the headline feature for a streaming LLM response — we don't stream), already-better-handled-by-the-architectural-difference (we're FastAPI, they're aiohttp), or downstream-feature work we'd flag as future AIDLC tickets anyway.

---

## What we have today (the baseline)

`backend/app/adapters/line/{base,mock,real,_factory}.py` and `backend/app/routers/line_webhook.py` give us:

- ✅ HMAC-SHA256 webhook signature verification (constant-time compare, raw bytes)
- ✅ Raw bytes read **before** JSON parse
- ✅ Single mocked + real-stub adapter pair behind a Protocol
- ✅ `send_reply(line_user_id, text)` outbound API on the Protocol
- ✅ Idempotency via `event_id` scan over `messages.raw_data`
- ✅ Find-or-create lead by `line_user_id`
- ✅ SettingsDep per-request (post-Tier-1)
- ✅ Active-user fallback for `LINE_DEFAULT_AGENT_ID`
- ✅ Empty-payload path → 200 with `received: 0`
- ✅ Non-message / malformed events → silently logged + `processed: 0`
- ✅ 11 webhook tests passing

---

## What's in the hermes-agent adapter (1638 LOC)

Sections by feature. The ones marked **GAP** under our use case are the ones that need attention.

### 1. Webhook surface hardening

| Hermes-agent feature | Our state | Verdict |
|---|---|---|
| Constant-time `hmac.compare_digest` | ✅ same | — |
| Raw body verified before JSON parse | ✅ same | — |
| **1 MiB body cap** (`len(body) > WEBHOOK_BODY_MAX_BYTES` → 413) | ❌ **GAP** | **Fix** — protects against memory-exhaustion / crafted `Content-Length`. Trivial to add. |
| `webhookEventId` LRU dedup | ✅ (we use `event_id`, same idea) | — |
| Async event dispatch wrapped in `try/except` → never crashes the webhook | ✅ (`logger.exception` + skip) | — |
| Two profiles binding same channel access token → lock | n/a — we have one agent | Defer |
| **Self-message filter** (`sender_user_id == self._bot_user_id`) | ❌ **GAP** | **Fix** — when real LINE is wired, our outbound `send_reply` will produce webhook events on the receiving channel; without the filter the bot would reply to itself in an infinite loop. Tiny to add (~5 lines). |
| `/health` endpoint at the same path | ✅ (we have it at `/health`) | — |
| `aiohttp.web.AppRunner` lifecycle | ❌ we use uvicorn | n/a |

### 2. Inbound event types

| Event | Their handler | Our handler | Verdict |
|---|---|---|---|
| `message` (text / image / audio / video / file / sticker / location) | full parsing + media download + `MessageType` enum | text only; everything else falls through to "ignored" via `process_event` returning `reason="non_message"` for non-message types **and** within messages, anything that isn't `type=text` is dropped | **GAP — partial**. We should at least store the inbound `message.type` so future feature work doesn't need a re-fetch. |
| `postback` (tap of Template Button) | deserialises JSON, fetches from request cache, sends fresh reply → DELIVERED | not handled (still `process_event`'s "non_message" branch because `type=postback` ≠ `message`) | **Skip — slow-LLM button feature is N/A for us** |
| `follow` / `unfollow` / `join` / `leave` | logged | logged (via `process_event`) | — |
| `unsend` (message deletion) | not handled in their dispatch either | not handled | **GAP — small**. When a customer deletes their message in LINE we should mark `messages.is_withdrawn` (we don't have the column; a future addition). Easy to add column + handler. Defer unless users complain. |
| `accountLink` / `memberJoined` / `memberLeft` / `things` | not handled | not handled | Defer (no LIFF account linking, no IoT) |

### 3. Source resolution (chat type inference)

| Hermes-agent feature | Our state | Verdict |
|---|---|---|
| `_resolve_chat(source) -> (chat_id, 'dm' / 'group' / 'channel')` | parses `U` / `C` / `R` prefixes | ❌ **GAP** — we only look at `source.userId`. A group message has `source.type='group'` + `source.groupId`, no `userId`. We currently treat group messages as if the line_user_id were a `userId`. **Should at minimum store the source-type so we can route correctly later.** |
| Three-allowlist gating (`_allowed_for_source`) | ❌ **GAP** — but **Defer** (single-tenant MVP) | Add when multi-tenant / multi-channel is real. ~30 lines. |

### 4. Outbound send — Reply token + Push fallback

This is the headline correctness gap:

| Hermes-agent feature | Our state | Verdict |
|---|---|---|
| Cache `replyToken` from each inbound message (free, single-use, ~60s TTL) | ❌ **GAP** — our `send_reply` ignores `replyToken` (mock just records; real stub throws NotImplementedError) | **Fix**. When wiring real LINE, prefer Reply (free) and fall back to Push (metered). |
| Try Reply first, fall back to Push on token-missing-or-rejected | ❌ **GAP** | **Fix** — same code path as above. |
| `_consume_reply_token(chat_id)` returns token + flag indicating reply-vs-push | ❌ **GAP** | part of fix |
| Push fallback exception caught + retried via push | n/a in our case (real adapter NotImplemented) | part of fix |

This is a small piece of real wiring we should add. ~30-40 lines on the real stub. The mock is already correct because it records both paths.

### 5. Content / message transformation on outbound

| Hermes-agent feature | Our state | Verdict |
|---|---|---|
| Strip Markdown preserving URLs (`# ` headers, `*` emphasis, etc. — LINE doesn't render markdown) | ❌ **GAP** — our `send_reply` passes the agent's text verbatim. When wired, **`**bold**` would render literally in LINE. | **Fix** — add `strip_markdown_preserving_urls()` helper in `ai/` or `line/`. ~15 lines. |
| Split long text at 4500 chars, capped at 5 messages per call (LINE per-bubble 5000; per-Push 5-message max) | ❌ **GAP** — we send one big string; LINE would 400 with "message too long" if real | **Fix** — `split_for_line(text, max_chars=4500)` then chunk into `len(messages) <= 5` batches. ~25 lines. |
| `_is_system_bypass(content)` for steering messages | n/a for our domain | skip |

### 6. Media inbound + outbound

| Hermes-agent feature | Our state | Verdict |
|---|---|---|
| Download inbound `image`/`audio`/`video`/`file` via `/message-content/{messageId}` | ❌ **GAP** — we drop non-text messages | Defer until listing creation needs photos from the LINE conversation. We have a separate `/api/upload-image` upload path today. |
| Send outbound image/voice/video with HTTPS URL serving (`/line/media/<token>/<file>` from the same aiohttp app, allowed-roots guard) | ❌ **GAP** — `send_image_file`/`send_voice`/`send_video` is not on our Protocol | Defer until we generate content cards with images. |
| `LINE_PUBLIC_URL` env var (override URL construction when bind is `0.0.0.0`) | ❌ — we have no media send → no need yet | Defer until media send |

### 7. Operational / runtime

| Feature | Our state | Verdict |
|---|---|---|
| `LINE_PUBLIC_URL` env | ❌ | Defer |
| `LINE_PORT` / `LINE_HOST` configurable webhook | Fixed (uvicorn) | n/a (FastAPI runs uvicorn — config via `uvicorn app.main:app --host ... --port ...`) |
| `LINE_ALLOW_ALL_USERS` dev escape hatch | ❌ | Defer |
| `LINE_HOME_CHANNEL` (default outbound for cron/notification) | ❌ | Defer |
| Settings-driven `interactive_setup()` wizard | ❌ | n/a (we're FastAPI not a CLI; config is via `.env` or `.env.example`) |

### 8. Things we should NOT copy

- **Plugin-form / auto-discovery** — our app uses a single monolith with explicit `main.py` router wiring. Don't try to be a plugin.
- **aiohttp** — we have FastAPI/starlette. Adding aiohttp is dead weight.
- **`strip_markdown_preserving_urls()` style rewrite** — apply only the outbound transform, not the regex-heavy URL preservation. LINE *does* render URLs cleanly even when wrapped in markdown syntax; the right move is strip the marks but keep the URL bare.
- **Slow-LLM postback + RequestCache state machine** — only valuable if/when our `/api/listings` becomes async-streaming. We're request-response today.
- **`BasePlatformAdapter` inheritance** — we use Protocol composition; don't add class inheritance.
- **Three-allowlist gating** — single-tenant MVP. Add when we have multiple agent users in the same deployment.

---

## What "Fix now" looks like — concrete patches

### Fix #1: body size cap

```python
# backend/app/routers/line_webhook.py

WEBHOOK_BODY_MAX_BYTES = 1 * 1024 * 1024  # 1 MiB

async def line_webhook(request: Request, settings: SettingsDep, db: DBDep):
    body = await request.body()
    if len(body) > WEBHOOK_BODY_MAX_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="payload too large",
        )
    # ... existing signature + parse logic
```

~5 lines.

### Fix #2: self-message filter

When wiring real LINE, on connection fetch our bot's own `userId` and stash it:

```python
# inside LineRealAdapter.send_reply (when wired)
async def send_reply(self, line_user_id, text):
    if self._bot_user_id and line_user_id == self._bot_user_id:
        return  # ignore self-echo
    ...POST to /v2/bot/message/reply or /push...
```

~5 lines. Not a problem on the mock — it just stores everything. But on real, this is the difference between a working bot and an infinite loop.

### Fix #3: reply-token cache + Push fallback

Real LINE adapter changes (when wired). Sketch:

```python
# backend/app/adapters/line/real.py

class LineRealAdapter:
    def __init__(self, channel_secret, channel_access_token, ...):
        ...
        self._reply_tokens: dict[str, tuple[str, float]] = {}  # chat_id → (token, expiry)
        # fetch bot user-id at register-time, set self._bot_user_id

    async def send_reply(self, line_user_id, text):
        text = strip_markdown_preserving_urls(text)
        chunks = split_for_line(text, max_chars=4500)[:5]
        ...
        # try reply token first (cache from last inbound msg), fall back to push
```

When wiring is real, this is non-trivial (~40 lines + the dispatcher in `lead_pipeline` would need to write the reply_token onto a row). Today's mock can stub it.

### Fix #4: chunking helper

```python
# backend/app/adapters/line/base.py (shared helpers)

MAX_MESSAGES_PER_CALL = 5
LINE_SAFE_BUBBLE_CHARS = 4500

def split_for_line(text: str, max_chars: int = LINE_SAFE_BUBBLE_CHARS) -> list[str]:
    """Naive chunk: prefer paragraph, then sentence, then char."""
    if len(text) <= max_chars:
        return [text]
    # ...paragraph / sentence / char fallback...
    return chunks[:MAX_MESSAGES_PER_CALL]
```

~15 lines. Add to `line/base.py` so both mock and real get it.

### Fix #5: `unsend` event handling

Small but real. In `lead_pipeline.py::process_event`:

```python
if event.get("type") != "message":
    return ProcessResult(..., reason="non_message")

# Add: type-specific routing
msg = event.get("message") or {}
if msg.get("type") == "unsend":
    mark_withdrawn(msg.get("id"), db)  # store the redacted note; UI can hide later
    return ProcessResult(..., reason="unsend")

# existing text / lead creation...
```

Requires adding an `is_withdrawn` column to `messages` (one migration) and a column to the schema python mirror. Defer unless users ask.

---

## Verdict + suggested action

If we want to land **only the high-leverage fixes**, the smallest coherent PR would:

1. **Body size cap** (3-5 lines)
2. **`unsend` event graceful handling** (defer; this PR nothing)
3. **Markdown strip + chunking helpers added to `line/base.py`** (used by future real adapter; tested via unit test on a mock that exercises chunking boundaries; 30 lines + tests)
4. **Self-message filter stub** (5 lines in real adapter — exercises the path even on mock)

That's ~50 lines of code + ~20 lines of tests. The reply-token cache + Push fallback is the only medium piece; it goes in **only when we wire the real adapter** because the mock already covers "send a reply" semantics.

I'd tag the rest of the table above (allowlists, media inbound, media send, loading indicator, webhook port env, public URL env, slow-LLM button, account link, things, memberJoined/Left) as **future AIDLC tickets** that will surface when users ask for them. None of them is blocking today's MVP demo.

---

## TL;DR for the PR description

> Reviewed [hermes-agent#23197](https://github.com/NousResearch/hermes-agent/pull/23197) to mine for patterns relevant to our mocks-first Thai real-estate LINE integration. We're folding 4 items into the next backend PR: (1) body-size cap, (2) outbound Markdown strip + LINE chunking helpers, (3) self-message filter + reply-token cache on the real adapter, (4) ``LineDep`` wiring so the dispatcher can cache reply tokens off inbound events. Reply-token cache + Push fallback is the one substantive real adapter work; we'll add the actual HTTP dispatch when we wire the real client. Everything else (allowlists, media, slow-LLM button, account-link, things, ``unsend``) is N/A or future-work — flagged as AIDLC tickets.
