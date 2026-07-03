# Adapters

Four integration points, four identical contract patterns. Each pair shares a
Protocol; switching mocks → real services is a single env flag flip.

## The contract

```
adapters/<name>/
  ├── base.py        Protocol + DTOs + (optional) shared helpers
  ├── mock.py        in-process implementation, used by default in dev/tests
  ├── <real>.py      httpx client against the real service (stub for MVP)
  ├── _factory.py    build_<adapter>(settings) -> Adapter
  └── __init__.py    public re-exports

Note: the naming convention isn't strictly uniform. Supabase & LINE put the
real impl in `real.py`; AI splits per-provider
(`anthropic_real.py`, `gemini_real.py`); Storage calls it
`supabase_real.py`. The factories are uniform — they import the right file
regardless of name.
```

The factory reads `Settings` and returns the appropriate class. No router ever
references a concrete class by name — only the Protocol.

## Map

| Adapter         | Protocol               | Mock                                       | Real (status)                |
|-----------------|------------------------|--------------------------------------------|-------------------------------|
| **Supabase DB** | `SupabaseAdapter`      | `MockSupabaseAdapter` (process singleton)  | ✅ **Shipped** — PostgREST CRUD via httpx |
| **AI**          | `AiAdapter` (fallback chain) | `AnthropicMockAdapter` + `GeminiMockAdapter` | ✅ **Shipped (Anthropic)** — Claude 3.5 Sonnet via SDK; Gemini stub |
| **LINE**        | `LineAdapter`          | `LineMockAdapter` (sign/verify/send_reply) | ✅ **Shipped** — Reply/Push via httpx + bot-info cache + Markdown strip + chunker |
| **Storage**     | `StorageAdapter`       | `LocalStorageAdapter` (var/uploads/)       | ✅ **Shipped** — Supabase Storage upload + public/signed URL |

## Switching from mock to real

`.env` (see `backend/.env.example`):

```bash
USE_MOCKS=true                  # master switch — when true, mocks win even
                               # if individual USE_REAL_* flags are set.
                               # Set to false only when rolling out real services.

USE_REAL_SUPABASE=false        # real Supabase DB + Storage
USE_REAL_LINE=false             # real LINE Messaging API
USE_REAL_AI=false               # real Anthropic + Gemini

# Required for the real adapters you turn on:
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service-role>
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=AIza...
LINE_CHANNEL_SECRET=...
LINE_CHANNEL_ACCESS_TOKEN=...

# Required for the LINE webhook (real LINE is multi-tenant):
LINE_DEFAULT_AGENT_ID=<uuid-of-the-agent>
```

There is no order of operations. The factory reads settings at request time
via `request.app.state.settings`, so changing the env and restarting the
process is sufficient.

## Why mock-then-real, not one-big-real-client

1. **CI has zero API keys**. Mock clients make every test offline.
2. **Local dev uses zero API keys**. Same code path as test runs.
3. **The real adapter is a stub now** ~~stub~~ ✅ **fully wired**. When the
   production rollout happens, the only change is flipping env flags —
   `app/routers/*` and tests do not change.
4. **The fallback chain proves itself in tests**. `tests/test_ai_generator.py`
   injects a `_FailingAdapter` and asserts the secondary runs.

## Verifying the real adapters implement the Protocol

`tests/test_real_swap.py` is gated by `@pytest.mark.real_adapter`. It runs
under `RUN_REAL_ADAPTER_TESTS=1`:

```bash
RUN_REAL_ADAPTER_TESTS=1 pytest -m real_adapter
```

What it does:
- Instantiates each `*_real` class with placeholder config.
- `assert isinstance(real, Protocol)` — proves the wire is complete.
- Calls `sign_line_webhook` / `verify_line_webhook` and asserts round-trip.

## Per-adapter behaviour matrix

### SupabaseAdapter
- `query(table, filters=..., order_by=..., limit=..., offset=...) -> list[dict]`
- `count(table, filters=...) -> int`
- `insert(table, data) -> dict`   (auto-mints UUID + created_at defaults)
- `update(table, id, patch) -> dict | None`
- `delete(table, id) -> bool`
- `get_by_id(table, id) -> dict | None`

Mock returns deep-copied rows; mutations don't leak. The SQL ↔ mock parity
test (`test_sql_matches_mock_schema_tables`) catches schema drift.

### AiAdapter
- `model_name -> str`
- `generate(request: ListingRequest) -> GeneratedContent`

Two-tier exception model:
- `FallbackToNext` — transient; orchestrator tries next adapter.
- `BadRequest` — 4xx; surface immediately.

Mock templates are deterministic and templated on (property_type, platform);
assertion-friendly substrings (คอนโด, ตร.ม., ≥ 5 hashtags, etc.).

### LineAdapter
- `channel_secret -> str`
- `sign(body: bytes) -> str`  base64(HMAC-SHA256(secret, body))
- `verify(body, signature) -> bool`  constant-time
- `send_reply(line_user_id, text) -> dict`

Webhook security property: signature is verified against **raw body bytes**
BEFORE JSON parsing. Body-tampering attacker cannot smuggle events past the
gate.

### StorageAdapter
- `upload(content, *, filename, content_type) -> StoredObject`
- `get(key) -> (bytes, content_type) | None`
- `delete(key) -> bool`

Mock writes to `{var_dir}/uploads/{key}`. Path-traversal defence rejects
`/`, `\`, `..`. Content-type allow-list rejects non-image MIME types.

## Where to find the code

| Integration | Protocol   | Mock impl            | Real impl             |
|-------------|------------|----------------------|------------------------|
| Database    | `app/adapters/supabase/base.py` | `mock.py` | `real.py` |
| AI          | `app/adapters/ai/base.py`         | `anthropic_mock.py`, `gemini_mock.py` | `anthropic_real.py`, `gemini_real.py` |
| LINE        | `app/adapters/line/base.py`       | `mock.py` | `real.py` |
| Storage     | `app/adapters/storage/base.py`    | `local_mock.py` | `supabase_real.py` |
