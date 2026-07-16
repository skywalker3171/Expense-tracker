"""
store.py — thin wrappers around Cloudant MCP and COS MCP tools.
All actual network I/O is handled by the MCP servers.
"""
from __future__ import annotations

import logging
import mimetypes
import os
from typing import Any

import config

log = logging.getLogger(__name__)


try:
    from mcp_client import call_tool  # injected by runtime
except ImportError:
    def call_tool(tool: str, **kwargs) -> Any:  # type: ignore
        raise NotImplementedError(f"MCP tool '{tool}' not available in local mode.")


# ---------------------------------------------------------------------------
# Cloudant
# ---------------------------------------------------------------------------

def upsert_expense(doc: dict) -> None:
    """
    Save (insert or update) a single expense document in Cloudant.
    Uses doc["id"] as the Cloudant _id.
    """
    call_tool(
        "cloudant_upsert",
        database=config.CLOUDANT_DB,
        document={**doc, "_id": doc["id"]},
    )
    log.debug("Upserted expense %s", doc["id"])


def query_expenses(selector: dict | None = None) -> list[dict]:
    """
    Query all expenses (or a subset via Mango selector).
    Default: return every document in the expenses DB.
    """
    result = call_tool(
        "cloudant_query",
        database=config.CLOUDANT_DB,
        selector=selector or {},
        fields=["id", "date", "merchant", "amount", "currency", "category",
                "source_type", "source_email_id", "created_at"],
        limit=10_000,
    )
    return result.get("docs", [])


# ---------------------------------------------------------------------------
# COS (S3-compatible)
# ---------------------------------------------------------------------------

def upload_attachment(
    *,
    email_id: str,
    filename: str,
    data: bytes,
) -> str:
    """
    Upload a raw attachment to the COS bucket.
    Key format: <email_id>/<filename>
    Returns the S3 object key.
    """
    key = f"{email_id}/{filename}"
    content_type, _ = mimetypes.guess_type(filename)
    content_type = content_type or "application/octet-stream"

    call_tool(
        "s3_put_object",
        bucket=config.COS_BUCKET,
        key=key,
        body=data,
        content_type=content_type,
    )
    log.info("Uploaded %s to COS bucket %s", key, config.COS_BUCKET)
    return key
