"""
pipeline.py — shared "process one file" core used by BOTH ingest paths:
  * the Gmail poller (main.py)
  * the web upload API (web/backend)

It uploads the raw file to COS, routes it to the right parser/model, and
upserts the resulting expenses into Cloudant — all scoped to a user_id.
"""
from __future__ import annotations

import logging

import router
import store

log = logging.getLogger(__name__)


def process_file(*, user_id: str, source_ref: str, filename: str,
                 mime_type: str, data: bytes) -> list[dict]:
    """Process a single uploaded/attached file for one user.

    Returns the list of stored expense docs.
    """
    # 1. Store the raw file in COS, namespaced by user.
    store.upload_attachment(user_id=user_id, source_ref=source_ref,
                            filename=filename, data=data)

    # 2. Route to the correct parser/model. Expenses already carry user_id.
    expenses = router.route(
        data=data,
        filename=filename,
        mime_type=mime_type,
        user_id=user_id,
        source_ref=source_ref,
    )

    # 3. Persist each expense (idempotent upsert on deterministic id).
    for doc in expenses:
        store.upsert_expense(doc)

    log.info("Processed %s for user %s -> %d expenses",
             filename, user_id, len(expenses))
    return expenses
