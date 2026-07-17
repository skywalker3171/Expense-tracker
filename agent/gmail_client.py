"""
gmail_client.py — thin wrapper around the Gmail MCP tools.
All actual HTTP/OAuth work is handled by the MCP server; this module just
provides clean Python functions that the rest of the agent calls.
"""
from __future__ import annotations

import logging
import os
import tempfile
from typing import Any

log = logging.getLogger(__name__)

# Label applied to messages after successful processing (idempotency guard).
PROCESSED_LABEL_NAME = "Processed"
_processed_label_id: str | None = None


# ---------------------------------------------------------------------------
# Internal MCP call shim
# ---------------------------------------------------------------------------
from mcp_client import call_tool


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_processed_label_id() -> str:
    """Return (and cache) the Gmail label ID for PROCESSED_LABEL_NAME.

    Uses the server's get_or_create_label tool so we don't need a
    separate list + create round-trip.
    """
    global _processed_label_id
    if _processed_label_id is not None:
        return _processed_label_id
    result = call_tool("get_or_create_label", name=PROCESSED_LABEL_NAME)
    _processed_label_id = str(result.get("id") or result.get("text", "").split("ID:")[1].split()[0])
    log.debug("Resolved '%s' label id: %s", PROCESSED_LABEL_NAME, _processed_label_id)
    return _processed_label_id


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_unprocessed_messages() -> list[dict]:
    """
    Return Gmail messages matching subject:Expense OR subject:Chart
    that have NOT been labelled 'Processed'.
    """
    query = f"(subject:Expense OR subject:Chart) -label:{PROCESSED_LABEL_NAME}"
    log.debug("Gmail query: %s", query)
    result = call_tool(
        "search_emails",
        query=query,
        maxResults=50,
    )
    log.info("search_emails raw result: %s", result)
    # The MCP server returns a plain-text block, one email summary per entry
    # separated by blank lines, each containing "ID: <id>" lines.
    # Fall back to structured keys if the server ever changes format.
    messages = result.get("messages") or result.get("emails")
    if messages is None:
        text = result.get("text", "")
        messages = _parse_search_text(text)
    log.info("Found %d messages matching query", len(messages))
    return messages


def _parse_search_text(text: str) -> list[dict]:
    """Parse the plain-text search_emails response into a list of {id, ...} dicts."""
    import re
    messages = []
    # Each result block is separated by a blank line (or just contiguous lines)
    # We only need the ID to fetch the full message later.
    for block in re.split(r"\n{2,}", text.strip()):
        m = re.search(r"^ID:\s*(\S+)", block, re.MULTILINE)
        if m:
            messages.append({"id": m.group(1)})
    return messages


def get_message(message_id: str) -> dict:
    """Fetch full message metadata + body."""
    result = call_tool("read_email", messageId=message_id)
    log.debug("read_email raw result: %s", str(result)[:500])
    text = result.get("text", "")
    if text:
        return _parse_read_email_text(message_id, text)
    return result


def _parse_read_email_text(message_id: str, text: str) -> dict:
    """
    Convert the plain-text read_email response into the payload dict shape
    that main.py expects (headers list + parts list with attachments).

    Example input:
        Thread ID: 19f6d13c0d846fc3
        Subject: Expense
        From: Alice <alice@example.com>
        To: Bob <bob@example.com>
        Date: Thu, 16 Jul 2026 18:37:30 -0400

        Attachments (1):
        - Expense.csv (text/csv, 0 KB, ID: ANGjdJ86yr...)
    """
    import re

    headers = []
    parts = []
    thread_id = None

    for line in text.splitlines():
        # Thread ID
        m = re.match(r"^Thread ID:\s*(.+)", line)
        if m:
            thread_id = m.group(1).strip()
            continue
        # Standard headers
        for hname in ("Subject", "From", "To", "Date", "Message-ID", "In-Reply-To"):
            m = re.match(rf"^{hname}:\s*(.+)", line, re.IGNORECASE)
            if m:
                headers.append({"name": hname, "value": m.group(1).strip()})
                break
        # Attachment line:  - filename (mime, size, ID: attachmentId)
        m = re.match(r"^-\s+(.+?)\s+\(([^,]+),\s*[^,]+,\s*ID:\s*(\S+)\)", line)
        if m:
            filename   = m.group(1).strip()
            mime_type  = m.group(2).strip()
            att_id     = m.group(3).rstrip(")")
            parts.append({
                "filename": filename,
                "mimeType": mime_type,
                "body": {"attachmentId": att_id},
                "parts": [],
            })

    return {
        "id":       message_id,
        "threadId": thread_id,
        "payload": {
            "headers": headers,
            "parts":   parts,
            "body":    {},
        },
    }


def get_attachment(message_id: str, attachment_id: str, filename: str = "attachment.bin") -> bytes:
    """Download an attachment and return raw bytes.

    The MCP server saves the file to disk and returns the path in its
    success text.  We pass an explicit savePath + filename so the write
    is deterministic, then read the file back and clean up.
    """
    import re as _re
    tmp_dir = tempfile.mkdtemp(prefix="expense_att_")
    # Sanitise filename so it is safe to use on the filesystem
    safe_name = _re.sub(r'[<>:"/\\|?*]', "_", filename) or "attachment.bin"
    result = call_tool(
        "download_attachment",
        messageId=message_id,
        attachmentId=attachment_id,
        savePath=tmp_dir,
        filename=safe_name,
    )
    text = result.get("text", "")
    log.debug("download_attachment result: %s", text[:200])

    # Server returns "Attachment downloaded successfully:\nFile: ...\nSaved to: <path>"
    saved_path = os.path.join(tmp_dir, safe_name)
    if not os.path.isfile(saved_path):
        # Try to extract path from success message as fallback
        m = _re.search(r"Saved to:\s*(.+)", text)
        if m:
            saved_path = m.group(1).strip()

    if not os.path.isfile(saved_path):
        raise RuntimeError(
            f"download_attachment failed: {text[:300]}"
        )

    with open(saved_path, "rb") as fh:
        data = fh.read()
    try:
        os.remove(saved_path)
        os.rmdir(tmp_dir)
    except OSError:
        pass
    return data


def mark_processed(message_id: str) -> None:
    """Apply the 'Processed' label and mark as read (idempotency)."""
    label_id = _get_processed_label_id()
    call_tool(
        "modify_email",
        messageId=message_id,
        addLabelIds=[label_id],
        removeLabelIds=["UNREAD"],
    )
    log.info("Marked message %s as Processed", message_id)


def send_reply(
    *,
    to: str,
    subject: str,
    html_body: str,
    thread_id: str | None = None,
    attachments: list[dict] | None = None,
) -> None:
    """
    Send an email reply (used for Chart responses).
    attachments: list of {"filename": str, "mime_type": str, "data": bytes}

    The MCP send_email tool takes file paths, so we write each attachment
    to a temp file and pass the path.
    """
    tmp_paths: list[str] = []
    try:
        for att in (attachments or []):
            suffix = os.path.splitext(att["filename"])[1] or ".bin"
            fd, path = tempfile.mkstemp(suffix=suffix, prefix="expense_reply_")
            with os.fdopen(fd, "wb") as fh:
                fh.write(att["data"])
            tmp_paths.append(path)

        kwargs: dict[str, Any] = {
            "to":       [to],
            "subject":  subject,
            "body":     html_body,

            "htmlBody": html_body,
            "mimeType": "text/html",
        }
        if thread_id:
            kwargs["threadId"] = thread_id
        if tmp_paths:
            kwargs["attachments"] = tmp_paths

        call_tool("send_email", **kwargs)
        log.info("Sent reply to %s subject='%s'", to, subject)
    finally:
        for path in tmp_paths:
            try:
                os.remove(path)
            except OSError:
                pass
