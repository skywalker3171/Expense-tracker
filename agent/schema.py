"""schema.py — canonical Expense data contract."""
import hashlib
import re
from datetime import datetime, timezone
from typing import Optional

from config import CATEGORIES

EXPENSE_KEYS = (
    "id", "type", "user_id", "date", "merchant", "amount", "currency",
    "category", "source_type", "source_ref", "source_email_id",
    "raw_text", "created_at",
)

_FR_MONTHS = {
    "janvier": 1, "janv": 1, "jan": 1, "fevrier": 2, "fevr": 2, "fev": 2,
    "mars": 3, "mar": 3, "avril": 4, "avr": 4, "mai": 5, "juin": 6,
    "juillet": 7, "juil": 7, "aout": 8, "septembre": 9, "sept": 9, "sep": 9,
    "octobre": 10, "oct": 10, "novembre": 11, "nov": 11, "decembre": 12, "dec": 12,
}
_EN_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "october": 10, "oct": 10,
    "november": 11, "december": 12,
}
_MONTHS = {**_EN_MONTHS, **_FR_MONTHS}


def make_id(user_id: str, source_ref: str, line_index: int) -> str:
    """Deterministic doc id: sha256(user_id + source_ref + line_index)."""
    raw = f"{user_id}:{source_ref}:{line_index}"
    return hashlib.sha256(raw.encode()).hexdigest()


def find_statement_year(text: str) -> Optional[int]:
    """Best-effort statement year from PDF text (e.g. 'au 30 juin 2026')."""
    if not text:
        return None
    years = [int(m.group()) for m in re.finditer(r"\b(?:19|20)\d{2}\b", text)]
    plausible = [y for y in years if 2000 <= y <= datetime.now().year + 1]
    return max(plausible) if plausible else None


def coerce_date(value: str, default_year: Optional[int] = None) -> str:
    """Normalise many date strings to YYYY-MM-DD; return as-is on failure.

    Handles full dates plus year-less "day month" / "month day" forms common on
    bank statements (English and French). When the source omits a year, use
    default_year (the statement period year) rather than letting a downstream
    model guess it.
    """
    if not value:
        return ""
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    yr = default_year or datetime.now().year
    low = s.lower().replace(".", " ").replace(",", " ")
    low = re.sub(r"\b(\d{1,2})(?:er|st|nd|rd|th)\b", r"\1", low)  # 1er/1st -> 1
    low = re.sub(r"\s+", " ", low).strip()
    tokens = low.split(" ")
    day = None
    mon = None
    for tok in tokens:
        if tok.isdigit() and 1 <= int(tok) <= 31 and day is None:
            day = int(tok)
        elif tok in _MONTHS and mon is None:
            mon = _MONTHS[tok]
    if day is not None and mon is not None:
        try:
            return datetime(yr, mon, day).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return s


def coerce_amount(value) -> float:
    """Strip currency symbols and cast to float; return 0.0 on failure."""
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    cleaned = re.sub(r"[^\d.]", "", str(value))
    try:
        return round(float(cleaned), 2)
    except ValueError:
        return 0.0


def _current_categories() -> list:
    """Editable global categories if available, else the config defaults."""
    try:
        import store
        return store.get_categories()
    except Exception:
        return list(CATEGORIES)


def normalize_merchant(merchant: str) -> str:
    """Normalize a merchant string into a stable key for category-rule matching."""
    if not merchant:
        return ""
    s = str(merchant).lower().strip()
    s = re.sub(r"#\s*\d+", " ", s)
    s = re.sub(r"\b(pos|purchase|debit|credit|card|txn|ref|no)\b", " ", s)
    s = re.sub(r"\d{2,}", " ", s)
    s = re.sub(r"[^a-z0-9&' ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def coerce_category(value: str) -> str:
    """Return value if it matches an allowed category (case-insensitive), else 'Other'."""
    cats = _current_categories()
    if value in cats:
        return value
    title = value.strip().title()
    if title in cats:
        return title
    return "Other"


def build_expense(
    *,
    user_id: str,
    source_ref: str,
    line_index: int,
    date: str,
    merchant: str,
    amount,
    currency: str = "CAD",
    category: str = "Other",
    source_type: str,
    flow: str = "withdrawal",
    raw_text: str = "",
    created_at: Optional[str] = None,
    default_year: Optional[int] = None,
) -> dict:
    """Construct and validate a canonical expense document."""
    return {
        "id":              make_id(user_id, source_ref, line_index),
        "type":            "expense",
        "user_id":         user_id,
        "date":            coerce_date(date, default_year),
        "merchant":        merchant.strip(),
        "amount":          coerce_amount(amount),
        "currency":        currency.upper() if currency else "CAD",
        "category":        coerce_category(category),
        "source_type":     source_type,
        "flow":            "deposit" if str(flow).strip().lower() == "deposit" else "withdrawal",
        "source_ref":      source_ref,
        "source_email_id": source_ref,
        "raw_text":        raw_text,
        "created_at":      created_at or datetime.now(timezone.utc).isoformat(),
    }


def validate_expense(doc: dict) -> list[str]:
    """Return a list of validation error strings (empty = valid)."""
    errors = []
    for key in EXPENSE_KEYS:
        if key not in doc:
            errors.append(f"Missing field: {key}")
    if not doc.get("user_id"):
        errors.append("user_id must be a non-empty string")
    if doc.get("amount", -1) < 0:
        errors.append("amount must be >= 0")
    if doc.get("source_type") not in ("pdf", "image", "csv"):
        errors.append(f"Invalid source_type: {doc.get('source_type')}")
    return errors
