"""
main.py — entrypoint for the expense agent.

Run modes:
  python main.py           → process one batch of unread expense emails (run_once)
  python main.py --loop    → poll every 10 minutes (local dev / non-CE deployment)

In IBM Code Engine, a cron subscription calls the /run HTTP endpoint (see bottom).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time

# Load secrets.env from the Infra folder (../Infra/ relative to agent/) if present.
# In Code Engine the vars are injected directly; this is a no-op there.
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "Infra", "secrets.env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("main")

import gmail_client
import router
import store
import chart


# ---------------------------------------------------------------------------
# Core poll cycle
# ---------------------------------------------------------------------------

def run_once() -> None:
    """Fetch unread expense/chart emails and process each one."""
    log.info("=== poll cycle start ===")
    messages = gmail_client.list_unprocessed_messages()
    log.info("Found %d unprocessed messages", len(messages))

    for msg_meta in messages:
        msg_id = msg_meta["id"]
        try:
            _process_message(msg_id)
        except Exception:
            log.exception("Failed to process message %s — skipping", msg_id)

    log.info("=== poll cycle end ===")


def _process_message(msg_id: str) -> None:
    message = gmail_client.get_message(msg_id)
    subject = _get_header(message, "Subject")
    sender  = _get_header(message, "From")
    thread_id = message.get("threadId")

    log.info("Processing message %s | subject='%s' | from=%s", msg_id, subject, sender)

    subject_lower = subject.lower()

    # ── Chart request ──────────────────────────────────────────────────────
    if "chart" in subject_lower:
        _handle_chart_request(msg_id, sender, subject, thread_id)
        gmail_client.mark_processed(msg_id)
        return

    # ── Expense email ──────────────────────────────────────────────────────
    if "expense" in subject_lower:
        attachments = _get_attachments(message)
        if not attachments:
            log.warning("Message %s has no attachments — skipping", msg_id)
            gmail_client.mark_processed(msg_id)
            return

        for att in attachments:
            _handle_attachment(att, msg_id)

        gmail_client.mark_processed(msg_id)
        return

    log.warning("Message %s subject '%s' matched no handler", msg_id, subject)


def _handle_attachment(att: dict, msg_id: str) -> None:
    filename    = att["filename"]
    mime_type   = att["mime_type"]
    data        = gmail_client.get_attachment(msg_id, att["attachment_id"], att["filename"])

    # 1. Upload raw file to COS
    store.upload_attachment(email_id=msg_id, filename=filename, data=data)

    # 2. Route to correct parser → list of expense dicts
    expenses = router.route(
        data=data,
        filename=filename,
        mime_type=mime_type,
        source_email_id=msg_id,
    )

    # 3. Store each expense in Cloudant
    for doc in expenses:
        store.upsert_expense(doc)

    log.info("Attachment %s → %d expenses stored", filename, len(expenses))


def _handle_chart_request(msg_id: str, sender: str, subject: str, thread_id: str | None) -> None:
    expenses = store.query_expenses()
    log.info("Chart request from %s — %d expenses in DB", sender, len(expenses))

    png_bytes, html_body = chart.build_chart_email(expenses)

    gmail_client.send_reply(
        to=_extract_email(sender),
        subject=f"Re: {subject}",
        html_body=html_body,
        thread_id=thread_id,
        attachments=[{
            "filename":  "expense-chart.png",
            "mime_type": "image/png",
            "data":      png_bytes,
        }],
    )
    log.info("Chart reply sent to %s", sender)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_email(addr: str) -> str:
    import re as _re
    m = _re.search(r"<([^>]+)>", addr or "")
    return m.group(1) if m else (addr or "").strip()


def _get_header(message: dict, name: str) -> str:
    headers = message.get("payload", {}).get("headers", [])
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _get_attachments(message: dict) -> list[dict]:
    """Walk the message payload and collect all non-empty attachment parts."""
    attachments = []
    _walk_parts(message.get("payload", {}), attachments)
    return attachments


def _walk_parts(part: dict, out: list) -> None:
    body = part.get("body", {})
    if part.get("filename") and body.get("attachmentId"):
        out.append({
            "filename":      part["filename"],
            "mime_type":     part.get("mimeType", "application/octet-stream"),
            "attachment_id": body["attachmentId"],
        })
    for sub in part.get("parts", []):
        _walk_parts(sub, out)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Expense agent")
    parser.add_argument("--loop", action="store_true",
                        help="Poll continuously every 10 minutes")
    args = parser.parse_args()

    if args.loop:
        log.info("Running in loop mode (every 600s)")
        while True:
            run_once()
            time.sleep(600)
    else:
        run_once()
