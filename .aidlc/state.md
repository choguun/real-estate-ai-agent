# AIDLC State

- **Phase**: implementing
- **Branch**: feat/real-adapter-wiring
- **PR**: (TBD)
- **Last action**: 2026-07-03T23:50:00Z
- **Next action**: Run /implement T-104 (Real Storage — Supabase Storage upload + signed URL)
- **Notes**: T-101 + T-102 + T-103 done. RealSupabaseAdapter (PostgREST),
  RealLineAdapter (Reply/Push API + bot-info cache + Markdown strip +
  self-message filter), AnthropicRealAdapter (Claude 3.5 Sonnet SDK
  with typed FallbackToNext/BadRequest mapping + versioned prompt V1).
  35 new tests, 172 total passing, coverage 92.99%.
  Starting T-104: real Supabase Storage upload (POST /storage/v1/object/
  {bucket}/{path}) returning public URL; bucket configurable via
  SUPABASE_STORAGE_BUCKET env (default 'uploads'); preserves the
  10MB cap + MIME allow-list from the mock.

_Updated: 2026-07-03T23:50:00Z_
