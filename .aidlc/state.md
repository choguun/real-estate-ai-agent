# AIDLC State

- **Phase**: implementing
- **Branch**: feat/month-1-mvp
- **PR**: 1
- **Last action**: 2026-07-03T07:15:00Z
- **Next action**: Run /implement T-003 (auth: signup / login / LIFF + JWT)
- **Notes**:
  - T-001 ✅ FastAPI + Next.js shells, /health, CI matrix, 3 tests.
  - T-002 ✅ Mock Supabase adapter + Protocol + factory + canonical SQL.
    - 25/25 tests pass. Coverage 91% on `app/`. ruff/mypy clean.
    - Adapter Protocol pattern proven — T-005/006/008 mirror this same shape.
    - `USE_REAL_SUPABASE=true` swaps in the stub real client (network calls deferred to tasks that need them).
  - 11 of 12 tasks remaining. Next load-bearing: T-003 auth (gates all subsequent routers).

_Updated: 2026-07-03T07:15:00Z_
