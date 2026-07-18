"""
watsonx_client.py — calls watsonx.ai (WML) for:
  1. Image / scanned-PDF OCR  → meta-llama/llama-3-2-11b-vision-instruct
  2. CSV / text-PDF normalize → ibm/granite-3-8b-instruct
"""
from __future__ import annotations

import base64
import json
import logging
import re
import time
from typing import Any

import requests

import config
from schema import build_expense, coerce_category, coerce_amount, coerce_date

log = logging.getLogger(__name__)


def _cats_str() -> str:
    """Comma-joined current category list (editable global), with fallback."""
    try:
        import store
        return ", ".join(store.get_categories())
    except Exception:
        return ", ".join(config.CATEGORIES)

_IAM_TOKEN_URL = "https://iam.cloud.ibm.com/identity/token"
_WML_BASE      = config.WATSONX_URL

# Model IDs
_VISION_MODEL  = "meta-llama/llama-3-2-11b-vision-instruct"
_TEXT_MODEL    = "ibm/granite-3-8b-instruct"

# Token cache
_token_cache: dict = {"token": None, "expires_at": 0.0}


# ---------------------------------------------------------------------------
# IAM auth
# ---------------------------------------------------------------------------

def _get_bearer_token() -> str:
    """Fetch (or return cached) IBM IAM bearer token."""
    if time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    resp = requests.post(
        _IAM_TOKEN_URL,
        data={
            "grant_type":    "urn:ibm:params:oauth:grant-type:apikey",
            "apikey":        config.WATSONX_APIKEY,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    _token_cache["token"]      = payload["access_token"]
    _token_cache["expires_at"] = time.time() + payload.get("expires_in", 3600)
    return _token_cache["token"]


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_get_bearer_token()}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }


# ---------------------------------------------------------------------------
# Generic chat helper
# ---------------------------------------------------------------------------

def _chat(model_id: str, messages: list[dict], max_tokens: int = 1024) -> str:
    """Call ml/v1/text/chat and return the assistant text content."""
    url = f"{_WML_BASE}/ml/v1/text/chat?version=2024-05-01"
    body = {
        "model_id":   model_id,
        "project_id": config.WATSONX_PROJECT_ID,
        "messages":   messages,
        "parameters": {
            "max_new_tokens": max_tokens,
            "temperature":    0.0,
        },
    }
    resp = requests.post(url, json=body, headers=_headers(), timeout=120)
    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        log.error("watsonx API error %s: %s", resp.status_code, resp.text[:500])
        raise
    return resp.json()["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# JSON extraction helper
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> Any:
    """Pull the first JSON array or object out of a freeform LLM response."""
    # Try direct parse first
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    # Find first [...] or {...}
    for pattern in (r"\[.*\]", r"\{.*\}"):
        match = re.search(pattern, stripped, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                continue
    # Salvage: the response is likely a JSON array truncated by max_new_tokens
    # (missing its closing "]"). Recover every complete top-level {...} object.
    salvaged = []
    for obj in re.findall(r"\{[^{}]*\}", stripped, re.DOTALL):
        try:
            salvaged.append(json.loads(obj))
        except json.JSONDecodeError:
            continue
    if salvaged:
        log.warning("Recovered %d objects from truncated LLM JSON", len(salvaged))
        return salvaged
    log.warning("Could not extract JSON from LLM response: %s", stripped[:300])
    return []


# ---------------------------------------------------------------------------
# 1. Vision OCR — image receipts
# ---------------------------------------------------------------------------

_VISION_SYSTEM = (
    "You are an expense-receipt OCR assistant. "
    "Extract every expense line from the receipt image and return ONLY a JSON array. "
    "Each element must have exactly these keys: "
    "date (YYYY-MM-DD), merchant (string), amount (number), currency (3-letter ISO), "
    "category (one of: {cats}). "
    "If a field is not visible, use sensible defaults: date=today, currency=CAD, category=Other. "
    "Return [] if no expense is found. No markdown, no explanation."
)


def parse_image_receipt(
    image_bytes: bytes,
    *,
    user_id: str,
    source_ref: str,
    filename: str,
) -> list[dict]:
    """
    Send a receipt image to Llama-3.2-11b-vision-instruct and return
    a list of canonical expense dicts.
    """
    b64 = base64.b64encode(image_bytes).decode()
    # Guess MIME type from filename extension
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "png"
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/png")

    messages = [
        {"role": "system", "content": _VISION_SYSTEM.format(cats=_cats_str())},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                {"type": "text",      "text": "Extract all expense lines from this receipt."},
            ],
        },
    ]

    raw_text = _chat(_VISION_MODEL, messages, max_tokens=2048)
    rows = _extract_json(raw_text)
    if not isinstance(rows, list):
        rows = [rows] if isinstance(rows, dict) else []

    expenses = []
    for idx, row in enumerate(rows):
        doc = build_expense(
            user_id=user_id,
            source_ref=source_ref,
            line_index=idx,
            date=row.get("date", ""),
            merchant=row.get("merchant", "Unknown"),
            amount=row.get("amount", 0),
            currency=row.get("currency", "CAD"),
            category=row.get("category", "Other"),
            source_type="image",
            raw_text=raw_text,
        )
        expenses.append(doc)

    log.info("Vision OCR %s → %d expenses", filename, len(expenses))
    return expenses


# ---------------------------------------------------------------------------
# 2. Granite — CSV / text-PDF categorization
# ---------------------------------------------------------------------------

_TEXT_SYSTEM = (
    "You are an expense-data normalization assistant. "
    "Given raw expense text (CSV rows or PDF content), extract every expense line "
    "and return ONLY a JSON array. "
    "Each element must have exactly these keys: "
    "date (YYYY-MM-DD), merchant (string), amount (number), currency (3-letter ISO), "
    "category (one of: {cats}), "
    "flow (either 'withdrawal' for Retrait/debit lines or 'deposit' for Dépôt/deposit/credit lines). "
    "Normalize amounts to numbers (strip $ signs). "
    "Map each line to the best matching category; use Other if unsure. "
    "Return [] if no expenses are found. No markdown, no explanation."
)


def categorize_text(
    *,
    text: str,
    source_type: str,
    source_email_id: str,
) -> list[dict]:
    """
    Send CSV / text-PDF content to Granite and return raw normalized rows
    (dicts with date, merchant, amount, currency, category).
    The caller wraps them into canonical expense docs via build_expense().
    """
    messages = [
        {"role": "system", "content": _TEXT_SYSTEM.format(cats=_cats_str())},
        {"role": "user",   "content": f"Extract expenses from the following {source_type} content:\n\n{text}"},
    ]

    raw_text = _chat(_TEXT_MODEL, messages, max_tokens=4096)
    rows = _extract_json(raw_text)
    if not isinstance(rows, list):
        rows = [rows] if isinstance(rows, dict) else []

    log.info("Granite %s → %d rows", source_type, len(rows))
    return rows
