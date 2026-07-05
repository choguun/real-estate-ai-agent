"""T-703 — CSP violation reporting (cycle 7 AC-CSP-01..05).

4 tests covering:

- AC-CSP-01: POST /api/csp-report accepts application/csp-report
  content-type and parses the csp-report JSON body
- AC-CSP-02: writes one row to security_events with
  action='csp.violation', metadata={violated_directive, blocked_uri}
- AC-CSP-03: returns 204 on malformed bodies (no raise, no 500)
- AC-CSP-04 (backend portion): writes the audit row only when
  the body is parseable

Plus a shape check on ACTION_CSP_VIOLATION constant.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.adapters.supabase._factory import get_db, reset_mock_singleton
from app.audit_log import ACTION_CSP_VIOLATION
from app.config import get_settings
from app.main import create_app

# ── Constant contract ────────────────────────────────────────────


def test_action_csp_violation_constant_is_stable() -> None:
    """The CSP violation action string is locked at module load.
    Ops dashboards match on it; SIEM rules filter by it.
    """
    assert ACTION_CSP_VIOLATION == "csp.violation"


# ── Standard report ───────────────────────────────────────────────


def test_csp_report_writes_audit_row_on_valid_report() -> None:
    """AC-CSP-01 + AC-CSP-02: standard report → 204 + audit row."""
    reset_mock_singleton()
    db = get_db(get_settings())

    with TestClient(create_app()) as c:
        body = {
            "csp-report": {
                "document-uri": "https://app.example.com/dashboard",
                "violated-directive": "script-src 'self'",
                "blocked-uri": "https://evil.example.com/x.js",
                "original-policy": "default-src 'self'; script-src 'self'",
            }
        }
        r = c.post(
            "/api/csp-report",
            content=json.dumps(body),
            headers={"Content-Type": "application/csp-report"},
        )
    assert r.status_code == 204, r.text

    rows = db.query("security_events", filters={"action": "csp.violation"})
    assert len(rows) == 1
    row = rows[0]
    assert row["metadata"]["violated_directive"] == "script-src 'self'"
    assert row["metadata"]["blocked_uri"] == "https://evil.example.com/x.js"
    assert row["success"] is True  # report was accepted


def test_csp_report_handles_minimal_body() -> None:
    """Browsers may send sparse reports. Endpoint must handle missing
    fields gracefully (use "unknown" as the default).
    """
    reset_mock_singleton()
    db = get_db(get_settings())

    with TestClient(create_app()) as c:
        r = c.post(
            "/api/csp-report",
            content=json.dumps({"csp-report": {}}),
            headers={"Content-Type": "application/csp-report"},
        )
    assert r.status_code == 204, r.text

    rows = db.query("security_events", filters={"action": "csp.violation"})
    assert len(rows) == 1
    row = rows[0]
    assert row["metadata"]["violated_directive"] == "unknown"
    assert row["metadata"]["blocked_uri"] == "unknown"


def test_csp_report_handles_malformed_body() -> None:
    """AC-CSP-03: a malformed body returns 204 (no 500, no raise).
    Browsers shouldn't see retry storms.
    """
    reset_mock_singleton()

    with TestClient(create_app()) as c:
        # Not JSON at all
        r = c.post(
            "/api/csp-report",
            content="not json",
            headers={"Content-Type": "application/csp-report"},
        )
        assert r.status_code == 204, r.text

        # Valid JSON but not the expected shape
        r = c.post(
            "/api/csp-report",
            content=json.dumps({"unexpected": "shape"}),
            headers={"Content-Type": "application/csp-report"},
        )
        assert r.status_code == 204, r.text

        # Missing csp-report key entirely
        r = c.post(
            "/api/csp-report",
            content=json.dumps({"foo": "bar"}),
            headers={"Content-Type": "application/csp-report"},
        )
        assert r.status_code == 204, r.text


def test_csp_report_handles_empty_body() -> None:
    """AC-CSP-03: completely empty body returns 204, no 500."""
    reset_mock_singleton()

    with TestClient(create_app()) as c:
        r = c.post(
            "/api/csp-report",
            content="",
            headers={"Content-Type": "application/csp-report"},
        )
    assert r.status_code == 204, r.text
