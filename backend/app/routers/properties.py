"""Property router — list/create/get/update + soft-delete (archive)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status

from app.deps import CurrentUserIdDep, DBDep
from app.domain.property import Property, PropertyCreate, PropertyUpdate

router = APIRouter(prefix="/api/properties", tags=["properties"])


# ─── Helpers ────────────────────────────────────────────────────────────
def _scope(db: Any, property_id: str, user_id: str) -> dict[str, Any]:
    """Return the row if it belongs to `user_id`, else raise 404.

    404 (not 403) hides existence — prevents cross-user id probing.
    """
    row: dict[str, Any] | None = db.get_by_id("properties", property_id)
    if row is None or row.get("user_id") != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Property not found")
    return row


# ─── List ───────────────────────────────────────────────────────────────
@router.get("", response_model=list[Property])
def list_properties(
    db: DBDep,
    user_id: CurrentUserIdDep,
    status_filter: str | None = Query(default=None, alias="status"),
    include_archived: bool = Query(default=False),
) -> list[dict[str, Any]]:
    rows = db.query("properties", filters={"user_id": user_id})
    if status_filter is not None:
        rows = [r for r in rows if r.get("status") == status_filter]
    elif not include_archived:
        rows = [r for r in rows if r.get("status") != "archived"]
    rows.sort(key=lambda r: (r.get("updated_at") or "", r.get("created_at") or ""), reverse=True)
    return rows


# ─── Get ────────────────────────────────────────────────────────────────
@router.get("/{property_id}", response_model=Property)
def get_property(property_id: str, db: DBDep, user_id: CurrentUserIdDep) -> dict[str, Any]:
    return _scope(db, property_id, user_id)


# ─── Create ─────────────────────────────────────────────────────────────
@router.post("", response_model=Property, status_code=status.HTTP_201_CREATED)
def create_property(
    payload: PropertyCreate,
    db: DBDep,
    user_id: CurrentUserIdDep,
) -> dict[str, Any]:
    data = payload.model_dump(exclude_none=True)
    if "property_type" in data:
        data["property_type"] = data["property_type"].value
    return db.insert("properties", {"user_id": user_id, **data})


# ─── Update (PATCH) ─────────────────────────────────────────────────────
@router.patch("/{property_id}", response_model=Property)
def update_property(
    property_id: str,
    payload: PropertyUpdate,
    db: DBDep,
    user_id: CurrentUserIdDep,
) -> dict[str, Any]:
    _scope(db, property_id, user_id)  # 404 on cross-user or missing
    data = payload.model_dump(exclude_none=True)
    if "property_type" in data:
        data["property_type"] = data["property_type"].value
    if "status" in data:
        data["status"] = data["status"].value
    updated = db.update("properties", property_id, data)
    if updated is None:
        # Race: row vanished between scope-check and update.
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Property not found")
    return updated


# ─── Archive (idempotent soft-delete) ───────────────────────────────────
@router.post("/{property_id}/archive", response_model=Property)
def archive_property(property_id: str, db: DBDep, user_id: CurrentUserIdDep) -> dict[str, Any]:
    _scope(db, property_id, user_id)
    updated = db.update("properties", property_id, {"status": "archived"})
    if updated is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Property not found")
    return updated
