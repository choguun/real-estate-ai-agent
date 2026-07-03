# AIDLC State

- **Phase**: implementing
- **Branch**: feat/month-1-mvp
- **PR**: 1
- **Last action**: 2026-07-03T09:00:00Z
- **Next action**: Run /implement T-009 (LINE → Lead + Message pipeline, idempotent)
- **Notes**:
  - T-001 through T-008 ✅.
  - T-008 ✅ mock LINE adapter + signed webhook:
    - 107/107 backend tests, 94% coverage.
    - Signature verified against **raw request bytes** via
      `hmac.compare_digest`, BEFORE JSON parsing — the security
      property cannot be bypassed by body tampering.
    - 11 tests cover all rejection paths (missing/empty/wrong
      secret/tampered body) AND verify no DB writes occur on unverified
      requests (T-008's contract: gate-only, no event processing).
  - 4 of 12 tasks remaining. Next: T-009 wires the verified events into
    the lead + message pipeline (idempotency on event_id).

_Updated: 2026-07-03T09:00:00Z_
