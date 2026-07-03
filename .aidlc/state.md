# AIDLC State

- **Phase**: implementing
- **Branch**: feat/month-1-mvp
- **PR**: 1
- **Last action**: 2026-07-03T08:00:00Z
- **Next action**: Run /implement T-006 (mock AI adapter + /api/generate-listing)
- **Notes**:
  - T-001 ✅ scaffold + /health + CI.
  - T-002 ✅ mock Supabase adapter.
  - T-003 ✅ auth.
  - T-004 ✅ properties CRUD.
  - T-005 ✅ mock storage adapter + upload endpoint + PropertyForm + new page.
    - 70/70 backend tests, 14/14 frontend tests, 94% coverage.
    - Two design decisions worth flagging:
      1. `StorageAdapter` Protocol uses absolute URLs (from `public_base_url`)
         so it mirrors Supabase Storage behavior — not `/static/...` relative.
      2. `SettingsDep` now reads from `request.app.state.settings` so tests
         pass `Settings(public_base_url='http://testserver')` and the right
         prefix lands in upload URLs. Side benefit: no global cache collision
         between test runs.
    - Autouse fixture `_isolate_app_state` in test_storage.py resets the
      mock Supabase singleton per test (storage tests don't inject their
      own DB, they use the singleton).
  - 7 of 12 tasks remaining. Next is T-006 mock AI (generates Thai
    listing per property type + platform). T-007 will save those to
    `generated_listings` and add the detail page that uses PropertyForm's
    redirect destination.

_Updated: 2026-07-03T08:00:00Z_
