# AIDLC State

- **Phase**: shipping
- **Branch**: feat/real-adapter-wiring
- **PR**: [#3 Cycle 2 — Real adapter wiring](https://github.com/choguun/real-estate-ai-agent/pull/3) (open, 9 commits)
- **Last action**: 2026-07-04T01:00:00Z
- **Next action**: /ship (merge to main, delete branch)
- **Notes**:
  - /review complete: 5-axis review posted as PR comment.
    0 P0, 3 P1, 6 P2 — approve-with-minor-warnings.
  - P1s all addressed in `147bb82`:
    * P1-W1: Supabase `_safe_json` helper (typed error on malformed
      body, dict→list coercion)
    * P1-W2: Storage `get()` raises `StorageDownloadError` on 5xx
      (no longer silent None)
    * P1-W3: LINE `get_bot_user_id` 24h TTL (OA re-registration refresh)
  - Post-fix verification: 230 tests pass (+6 new), 10 skipped,
    0 failed; coverage still 93.04% ✅; ruff + mypy + format clean.
  - P2s (timeout consistency, magic numbers, retry/backoff, async
    variants, anthropic pin) deferred to follow-up.
  - 🎉 **Cycle 2 (real-adapter-wiring) complete** — all 5 tasks shipped.
  - All 4 real adapters now wire to real services via httpx:
    * Supabase DB → PostgREST CRUD with typed PermissionError
    * LINE → Reply/Push API w/ bot-info cache + Markdown strip + chunker
    * AI → Anthropic SDK (Claude 3.5 Sonnet) w/ FallbackToNext/BadRequest
      mapping + versioned prompt V1
    * Storage → Supabase Storage upload w/ public/signed URL + 10MB cap
  - Live smoke tests gated by RUN_LIVE_SMOKE=1; CI job runs on
    workflow_dispatch (manual) with GitHub Actions secrets
  - docs/adapters.md updated (all 4 rows: ✅ Shipped)
  - docs/production-deploy.md written (8-step walk-through)
  - **Verification (final, all 5 tasks):**
    - pytest: 184 tests pass, 7 skipped (real_swap + live_smoke opt-in)
    - coverage: 93.04% (≥ 80% gate) ✅
    - ruff + ruff-format: clean
    - mypy app/ strict: 0 issues across 53 files
  - Router code unchanged (AC-RW-08): 0 router files modified by this cycle.
  - To bring up real services: follow docs/production-deploy.md — flip
    USE_MOCKS=false + add credentials.

_Updated: 2026-07-04T00:30:00Z_

_Updated: 2026-07-04T00:30:00Z_
