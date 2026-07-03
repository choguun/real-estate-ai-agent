# AIDLC State

- **Phase**: implementing
- **Branch**: feat/month-1-mvp
- **PR**: 1
- **Last action**: 2026-07-03T07:30:00Z
- **Next action**: Run /implement T-004 (properties CRUD + list page)
- **Notes**:
  - T-001 ✅ scaffold + /health + CI.
  - T-002 ✅ mock Supabase adapter + Protocol + factory + canonical SQL.
  - T-003 ✅ auth: signup / login / LIFF / /me, bcrypt + JWT (HS256),
          /login & /signup pages with LINE LIFF stub button,
          (app)/dashboard placeholder for auth round-trip.
    - **Bug found + fixed during E2E:** `MockSupabaseAdapter` was per-request,
      so /signup-created users vanished by the time /me was called. Resolution:
      `_factory._get_or_init_mock()` is now a thread-safe process singleton.
      Tests still work because they use FastAPI `dependency_overrides`.
    - Schema tiny change: added `password_hash TEXT` to `users` for bcrypt
      storage. SQL ↔ mock parity test still passes.
    - 40/40 backend tests, 9/9 frontend tests. Coverage 94% on `app/`.
  - 9 of 12 tasks remaining. Next: T-004 properties (CRUD needs auth, the
    first auth-gated router).

_Updated: 2026-07-03T07:30:00Z_
