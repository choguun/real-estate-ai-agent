"""Storage router — upload image + serve /static/{key}."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import Response

from app.adapters.storage.base import (
    StoredObject,
    is_allowed_image,
)
from app.deps import CurrentUserIdDep, StorageDep

router = APIRouter(tags=["storage"])


@router.post(
    "/api/upload-image",
    response_model=StoredObject,
    status_code=status.HTTP_201_CREATED,
)
async def upload_image(
    file: Annotated[UploadFile, File(...)],
    storage: StorageDep,
    _user_id: CurrentUserIdDep,
) -> StoredObject:
    """Accept a single image and store it. Returns its public URL.

    Auth required. Allowed MIME types: image/jpeg, image/png, image/webp, image/gif.
    """
    filename = file.filename or "upload.bin"
    content_type = file.content_type or "application/octet-stream"
    if not is_allowed_image(filename, content_type):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only image/jpeg, image/png, image/webp, image/gif are allowed.",
        )

    content = await file.read()
    try:
        return storage.upload(
            content,
            filename=filename,
            content_type=content_type,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/static/{key}")
def get_static(key: str, storage: StorageDep) -> Response:
    """Serve an uploaded file. No auth (images are public to whoever has the URL)."""
    result = storage.get(key)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found")
    content, content_type = result
    return Response(content=content, media_type=content_type)
