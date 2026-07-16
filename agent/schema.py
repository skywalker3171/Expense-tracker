"""
schema.py — canonical Expense data contract.
Every parser/model must produce an Expense dict matching this shape before it
is stored in Cloudant.
"""
import hashlib
import re
from datetime import datetime, timezone
from typing import Optional

from config import CATEGORIES


# ---------------------------------------------------------------------------
# Canonical shape
# ---------------------------------------------------------------------------
EXPENSE_KEYS = (
    "id", "date", "merchant", "amount", "currency",
    "category", "source_type", "source_email_id",
    "raw_text", "created_at",
)


def make_id(source_email_id: str, line_index: int) -> str:
    """Deterministic doc id: sha256(email_id + line_index)."""
    raw = f"{source_email_id}:{line_index}"
    return hashlib.sha256(raw.encode()).hexdigest()


def coerce_date(value: str) -> str:
    """Try to normalise various date strings to YYYY-MM-DD; return as-is on failure."""
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(value.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # last-ditch: keep whatever the model returned
    return value.strip()


def coerce_amount(value) -> float:
    """Strip currency symbols and cast to float; return 0.0 on failure."""
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    cleaned = re.sub(r"[^\d.]", "", str(value))
    try:
        return round(float(cleaned), 2)
    except ValueError:
        return 0.0


def coerce_category(value: str) -> str:
    """Return value if it's in the fixed list, else 'Other'."""
    if value in CATEGORIES:
        return value
    # case-insensitive fallback
    title = value.strip().title()
    if title in CATEGORIES:
        return title
    return "Other"


def build_expense(
    *,
    source_email_id: str,
    line_index: int,
    date: str,
    merchant: str,
    amount,
    currency: str = "CAD",
    category: str = "Other",
    source_type: str,          # "pdf" | "image" | "csv"
    raw_text: str = "",
    created_at: Optional[str] = None,
) -> dict:
    """Construct and validate a canonical expense document."""
    return {
        "id":             make_id(source_email_id, line_index),
        "date":           coerce_date(date),
        "merchant":       merchant.strip(),
        "amount":         coerce_amount(amount),
        "currency":       currency.upper() if currency else "CAD",
        "category":       coerce_category(category),
        "source_type":    source_type,
        "source_email_id": source_email_id,
        "raw_text":       raw_text,
        "created_at":     created_at or datetime.now(timezone.utc).isoformat(),
    }


def validate_expense(doc: dict) -> list[str]:
    """Return a list of validation error strings (empty = valid)."""
    errors = []
    for key in EXPENSE_KEYS:
        if key not in doc:
            errors.append(f"Missing field: {key}")
    if doc.get("amount", -1) < 0:
        errors.append("amount must be >= 0")
    if doc.get("source_type") not in ("pdf", "image", "csv"):
        errors.append(f"Invalid source_type: {doc.get('source_type')}")
    return errors
