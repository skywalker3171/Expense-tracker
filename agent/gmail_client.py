"""
gmail_client.py — thin wrapper around the Gmail MCP tools.
All actual HTTP/OAuth work is handled by the MCP server; this module just
provides clean Python functions that the rest of the agent calls.
"""
from __future__ import annotations

import base64
import logging
from typing import Any

log = logging.getLogger(__name__)

# Label applied to messages after successful processing (idempotency guard)
PROCESSED_LABEL = "Processed"


# ---------------------------------------------------------------------------
# Internal MCP call shim
# The MCP tools are called via the agent runtime's tool-call interface.
# In local testing we import the mcp module directly; in production the
# Code Engine runtime injects the MCP client.
# ---------------------------------------------------------------------------
try:
    from mcp_client import call_tool  # injected by Code Engine / Bob runtime
except ImportError:
    # Local stub — replace with actual MCP client when available
    def call_tool(tool: str, **kwargs) -> Any:  # type: ignore
        raise NotImplementedError(f"MCP tool '{tool}' not available in local mode. "
                                  "Start the Gmail MCP server and inject mcp_client.")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_unprocessed_messages() -> list[dict]:
    """
    Return Gmail messages matching subject:Expense OR subject:Chart
    that are unread and have NOT been labelled 'Processed'.
    """
    result = call_tool(
        "gmail_list_messages",
        query="(subject:Expense OR subject:Chart) is:unread -label:Processed",
        max_results=50,
    )
    return result.get("messages", [])


def get_message(message_id: str) -> dict:
    """Fetch full message metadata + body."""
    return call_tool("gmail_get_message", message_id=message_id)


def get_attachment(message_id: str, attachment_id: str) -> bytes:
    """Download an attachment and return raw bytes."""
    result = call_tool(
        "gmail_get_attachment",
        message_id=message_id,
        attachment_id=attachment_id,
    )
    # Gmail API returns base64url-encoded data
    data = result.get("data", "")
    return base64.urlsafe_b64decode(data + "==")


def mark_processed(message_id: str) -> None:
    """Apply the 'Processed' label and mark as read (idempotency)."""
    call_tool(
        "gmail_modify_message",
        message_id=message_id,
        add_label_ids=[PROCESSED_LABEL],
        remove_label_ids=["UNREAD"],
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
    """
    encoded_attachments = []
    for att in (attachments or []):
        encoded_attachments.append({
            "filename":  att["filename"],
            "mime_type": att["mime_type"],
            "data":      base64.b64encode(att["data"]).decode(),
        })

    call_tool(
        "gmail_send_message",
        to=to,
        subject=subject,
        html_body=html_body,
        thread_id=thread_id,
        attachments=encoded_attachments,
    )
    log.info("Sent reply to %s subject='%s'", to, subject)
