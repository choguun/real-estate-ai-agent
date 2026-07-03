"""Generated-listings router — persist + edit + list per property.

T-304: scoped by `team_id` (the caller's current team) instead of
`user_id`. Within a team, all members see all listings for any
property owned by the team.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.deps import CurrentTeamIdDep, CurrentUserIdDep, DBDep
from app.domain.listing import (
    GeneratedListing,
    GeneratedListingCreate,
    GeneratedListingUpdate,
)

router = APIRouter(prefix="/api/listings", tags=["listings"])


def _scope_property(db: Any, property_id: str, team_id: str) -> dict[str, Any]:
    row: dict[str, Any] | None = db.get_by_id("properties", property_id)
    if row is None or row.get("team_id") != team_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Property not found")
    return row


def _scope_listing(db: Any, listing_id: str, team_id: str) -> dict[str, Any]:
    row: dict[str, Any] | None = db.get_by_id("generated_listings", listing_id)
    if row is None or row.get("team_id") != team_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Listing not found")
    return row


# ─── Create ─────────────────────────────────────────────────────────────
@router.post("", response_model=GeneratedListing, status_code=status.HTTP_201_CREATED)
def create_listing(
    payload: GeneratedListingCreate,
    db: DBDep,
    user_id: CurrentUserIdDep,
    team_id: CurrentTeamIdDep,
) -> dict[str, Any]:
    """Create a listing under the caller's current team.

    `user_id` is the creator (audit trail); `team_id` is the owner
    (tenant boundary for the listing).
    """
    _scope_property(db, payload.property_id, team_id)
    data = payload.model_dump()
    data["platform"] = data["platform"].value
    return db.insert(
        "generated_listings",
        {"user_id": user_id, "team_id": team_id, **data},
    )


# ─── List (per property) ───────────────────────────────────────────────
@router.get("", response_model=list[GeneratedListing])
def list_listings(
    db: DBDep,
    team_id: CurrentTeamIdDep,
    property_id: str = Query(...),
) -> list[dict[str, Any]]:
    _scope_property(db, property_id, team_id)
    rows = db.query("generated_listings", filters={"property_id": property_id})
    # Cross-team defense: even if a row has a different team_id (data
    # drift), drop it. RLS handles this on real Supabase; the mock
    # doesn't have RLS, so we filter here.
    rows = [r for r in rows if r.get("team_id") == team_id]
    rows.sort(key=lambda r: (r.get("platform") or "", r.get("created_at") or ""))
    return rows


# ─── Patch (editable fields) ────────────────────────────────────────────
@router.patch("/{listing_id}", response_model=GeneratedListing)
def update_listing(
    listing_id: str,
    payload: GeneratedListingUpdate,
    db: DBDep,
    team_id: CurrentTeamIdDep,
) -> dict[str, Any]:
    _scope_listing(db, listing_id, team_id)
    data: dict[str, Any] = payload.model_dump(exclude_none=True)
    if not data:
        # Empty patch is a no-op; return the current row.
        existing = db.get_by_id("generated_listings", listing_id)
        assert existing is not None  # already scoped above
        return existing
    updated = db.update("generated_listings", listing_id, data)
    if updated is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Listing not found")
    return updated


# ─── Delete ─────────────────────────────────────────────────────────────
@router.delete("/{listing_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_listing(listing_id: str, db: DBDep, team_id: CurrentTeamIdDep) -> Response:
    _scope_listing(db, listing_id, team_id)
    db.delete("generated_listings", listing_id)
    return Response(status_code=204)
