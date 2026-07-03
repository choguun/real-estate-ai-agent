# AIDLC State

- **Phase**: implementing
- **Branch**: feat/real-adapter-wiring
- **PR**: (TBD)
- **Last action**: 2026-07-04T00:10:00Z
- **Next action**: Run /implement T-105 (live smoke + CI opt-in + docs)
- **Notes**: T-101 + T-102 + T-103 + T-104 done. All 4 real adapters
  shipping: Supabase (PostgREST CRUD + RLS-error typing), LINE (Reply/Push
  + bot-info cache + Markdown strip + 5/4500 chunker + self-message
  filter), AI (Anthropic SDK + FallbackToNext/BadRequest mapping +
  versioned prompt V1), Storage (upload + public/signed URL + 10MB cap).
  47 new tests, 184 total passing, coverage 93.04%.
  Final task: T-105 — live smoke tests (RUN_LIVE_SMOKE=1 + workflow_dispatch),
  CI opt-in (real adapter tests in regular CI via MockTransport), docs
  (adapters.md updated, runbook.md 'Bring up real services' section,
  production-deploy.md).

_Updated: 2026-07-04T00:10:00Z_
