"""
routes_upload.py — receipt upload endpoint.
Runs the shared pipeline.process_file() scoped to the logged-in user.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

import config
import pipeline
from deps import current_user

router = APIRouter()


@router.post("/upload")
async def upload(file: UploadFile = File(...), user=Depends(current_user)):
    data = await file.read()
    max_bytes = config.MAX_UPLOAD_MB * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            f"file exceeds {config.MAX_UPLOAD_MB} MB limit")

    source_ref = f"upload-{uuid.uuid4().hex}"
    expenses = pipeline.process_file(
        user_id=user["id"],
        source_ref=source_ref,
        filename=file.filename or "upload.bin",
        mime_type=file.content_type or "application/octet-stream",
        data=data,
    )
    return {"count": len(expenses), "expenses": expenses}