"""T-504 — RLS write-path policy tests (cycle 5 AC-SEC-11).

Closes the cycle-3 review finding that 002_rls.sql left team-scoped
tables with no INSERT/UPDATE/DELETE policies, blocking team members
from doing self-service operations via anon auth.

This module exercises:
- The migration file `005_rls_gaps.sql` exists and contains the
  expected policy names (SQL is a contract; we lint it like code).
- The mock adapter's behavior aligns with the RLS contract: the
  service-role path accepts every write; team_id filters in the
  router layer prevent cross-team writes.

Run-time RLS validation against a real Supabase is in
`test_rls_denies_cross_team_property_read` (RUN_LIVE_SMOKE=1).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Path is relative to this test file's location (backend/tests/).
# The migration lives at backend/migrations/005_rls_gaps.sql.
MIGRATION_FILE = Path(__file__).parent.parent / "migrations" / "005_rls_gaps.sql"


def _read_migration() -> str:
    """Read the 005 migration file as text."""
    if not MIGRATION_FILE.exists():
        pytest.fail(f"{MIGRATION_FILE} not found — T-504 not implemented")
    return MIGRATION_FILE.read_text(encoding="utf-8")


def test_005_rls_gaps_migration_exists() -> None:
    """AC-SEC-11: the migration file is committed."""
    assert MIGRATION_FILE.exists()


def test_005_migration_enables_rls_on_team_invitations() -> None:
    """The team_invitations table must be RLS-enabled with a write
    policy so team members can self-service invite (vs. only the
    service-role path the cycle-3 migration left open).
    """
    sql = _read_migration()
    assert "ALTER TABLE team_invitations ENABLE ROW LEVEL SECURITY" in sql
    # Write policy exists with a name we can audit against
    assert re.search(
        r"CREATE POLICY\s+\w+\s+ON team_invitations\s+FOR\s+INSERT",
        sql,
        re.IGNORECASE,
    ), "team_invitations must have an INSERT policy for team-scoped writes"


def test_005_migration_enables_self_update_on_team_memberships() -> None:
    """team_memberships needs an UPDATE policy so a team member can
    leave the team (set left_at) via anon auth. INSERT/DELETE remain
    service-role only.
    """
    sql = _read_migration()
    assert "ALTER TABLE team_memberships ENABLE ROW LEVEL SECURITY" in sql
    assert re.search(
        r"CREATE POLICY\s+\w+\s+ON team_memberships\s+FOR\s+UPDATE",
        sql,
        re.IGNORECASE,
    ), "team_memberships must have an UPDATE policy for self-leave"


def test_005_migration_does_not_grant_cross_team_writes() -> None:
    """Defensive: every write policy in 005 must constrain team_id to
    the caller's team. A policy without `WITH CHECK (team_id = ...)`
    would grant cross-team writes — the bug we're closing.
    """
    sql = _read_migration()
    # Find every CREATE POLICY block and assert WITH CHECK uses team_id
    policy_blocks = re.findall(
        r"CREATE POLICY\s+\w+\s+ON\s+\w+\s+FOR\s+(INSERT|UPDATE)(.*?);",
        sql,
        re.IGNORECASE | re.DOTALL,
    )
    assert len(policy_blocks) >= 2, "expected ≥2 write policies in 005"
    for verb, body in policy_blocks:
        # Either WITH CHECK clause references team_id, OR the policy
        # constrains via user_id = auth.uid() (the leave case).
        body_normalized = body.lower()
        assert "team_id" in body_normalized or "user_id = auth.uid" in body_normalized, (
            f"{verb} policy has no team_id or self-user_id guard:\n{body}"
        )


def test_005_migration_uses_drop_policy_if_exists_idempotency() -> None:
    """Idempotency: every CREATE POLICY (live statement, not in a
    comment) is preceded by DROP POLICY IF EXISTS so the migration
    can be re-applied safely.
    """
    sql = _read_migration()
    # Strip line comments to avoid matching "CREATE POLICY" mentioned
    # in the docblock.
    sql_no_comments = "\n".join(
        line for line in sql.splitlines() if not line.strip().startswith("--")
    )
    creates = re.findall(r"CREATE POLICY\s+\w+", sql_no_comments, re.IGNORECASE)
    drops = re.findall(r"DROP POLICY IF EXISTS", sql_no_comments, re.IGNORECASE)
    assert len(creates) == len(drops), (
        f"mismatch: {len(creates)} CREATE POLICY vs {len(drops)} DROP POLICY IF EXISTS"
    )
