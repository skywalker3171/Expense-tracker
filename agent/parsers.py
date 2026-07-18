"""
parsers.py — extract expense rows from CSV and text-based PDF attachments.
CSV rows are sent to Granite for normalization/categorization.
Text PDFs are also sent to Granite.
"""
from __future__ import annotations

import io
import logging
import re

import pandas as pd
import pdfplumber

from schema import build_expense, validate_expense
import watsonx_client

log = logging.getLogger(__name__)


def _obfuscate_amount(amount) -> float:
    """Replace every digit of an amount's integer part with 1, preserving digit
    count and cents. Demo privacy for deposits: 2547 -> 1111, 55 -> 11, 345 -> 111.
    """
    try:
        val = float(amount)
    except (TypeError, ValueError):
        return 0.0
    whole = int(abs(val))
    digits = len(str(whole)) if whole > 0 else 1
    return float("1" * digits)


def _is_deposit(row: dict) -> bool:
    """True if the row is a deposit/credit (Dépôt) rather than a withdrawal
    (Retrait). Uses an explicit 'flow' field from the model, with a text fallback.
    """
    flow = str(row.get("flow", "")).strip().lower()
    if flow in ("deposit", "depot", "dépôt", "credit", "crédit"):
        return True
    if flow in ("withdrawal", "retrait", "debit", "débit"):
        return False
    # Fallback: scan the row's text fields for deposit keywords.
    blob = " ".join(str(v) for v in row.values()).lower()
    return ("dépôt" in blob or "depot" in blob or "deposit" in blob)


def _to_amount(cell) -> float:
    """Parse a money cell like '2 534.13' / '1,151.31' / '386.59' -> float, else 0."""
    if cell is None:
        return 0.0
    s = str(cell).strip().replace("\u00a0", " ").replace(" ", "").replace(",", "")
    s = re.sub(r"[^\d.]", "", s)
    try:
        return round(float(s), 2) if s else 0.0
    except ValueError:
        return 0.0


def _find_col(header, *names) -> int:
    """Return index of the first header cell containing any of the given names."""
    for i, cell in enumerate(header):
        low = str(cell or "").strip().lower()
        for n in names:
            if n in low:
                return i
    return -1


def _parse_bank_statement(pdf) -> list[dict]:
    """Column-aware parse of a bank statement with Retrait/Dépôt columns.

    Returns rows of {date, merchant, amount, flow}. Empty list if no such
    Retrait/Dépôt table layout is found (caller falls back to the LLM path).
    """
    out: list[dict] = []
    settings_variants = [
        {},
        {"vertical_strategy": "lines", "horizontal_strategy": "lines"},
        {"vertical_strategy": "text", "horizontal_strategy": "text"},
    ]
    for page in pdf.pages:
        tables = []
        for st in settings_variants:
            try:
                found = page.extract_tables(st) if st else page.extract_tables()
            except Exception:
                found = []
            if found:
                tables = found
                break
        for table in tables or []:
            if not table or len(table) < 2:
                continue
            header = table[0]
            ret_col = _find_col(header, "retrait")
            dep_col = _find_col(header, "dépôt", "depot", "dpt")
            date_col = _find_col(header, "date")
            desc_col = _find_col(header, "description")
            if ret_col < 0 or dep_col < 0:
                continue
            for r in table[1:]:
                ret_amt = _to_amount(r[ret_col]) if ret_col < len(r) else 0.0
                dep_amt = _to_amount(r[dep_col]) if dep_col < len(r) else 0.0
                if ret_amt <= 0 and dep_amt <= 0:
                    continue
                is_dep = dep_amt > 0
                amt = dep_amt if is_dep else ret_amt
                desc = str(r[desc_col]).strip() if 0 <= desc_col < len(r) and r[desc_col] else "Unknown"
                dt = str(r[date_col]).strip() if 0 <= date_col < len(r) and r[date_col] else ""
                out.append({
                    "date": dt,
                    "merchant": desc,
                    "amount": amt,
                    "flow": "deposit" if is_dep else "withdrawal",
                })
    return out


# --------------------------------------------------------------------------
# CSV parser
# --------------------------------------------------------------------------

def parse_csv(data: bytes, *, user_id: str, source_ref: str, filename: str) -> list[dict]:
    try:
        df = pd.read_csv(io.BytesIO(data))
    except Exception as exc:
        log.error("Failed to parse CSV %s: %s", filename, exc)
        return []

    if df.empty:
        log.warning("CSV %s is empty", filename)
        return []

    # Send the entire CSV text to Granite for structured extraction
    csv_text = df.to_csv(index=False)
    raw_rows = watsonx_client.categorize_text(
        text=csv_text,
        source_type="csv",
        source_email_id=source_ref,
    )

    expenses = []
    for idx, row in enumerate(raw_rows):
        doc = build_expense(
            user_id=user_id,
            source_ref=source_ref,
            line_index=idx,
            date=row.get("date", ""),
            merchant=row.get("merchant", "Unknown"),
            amount=row.get("amount", 0),
            currency=row.get("currency", "CAD"),
            category=row.get("category", "Other"),
            source_type="csv",
            raw_text=csv_text,
        )
        errs = validate_expense(doc)
        if errs:
            log.warning("Invalid expense from CSV row %d: %s", idx, errs)
        else:
            expenses.append(doc)

    log.info("CSV %s -> %d expenses", filename, len(expenses))
    return expenses


# ---------------------------------------------------------------------------
# Text-PDF parser
# ---------------------------------------------------------------------------

def parse_text_pdf(data: bytes, *, user_id: str, source_ref: str, filename: str) -> list[dict]:
    """
    Extract text from a text-layer PDF and send to Granite for normalization.
    """
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages_text = [page.extract_text() or "" for page in pdf.pages]
            bank_rows = _parse_bank_statement(pdf)
        full_text = "\n\n".join(pages_text).strip()
    except Exception as exc:
        log.error("Failed to extract text from PDF %s: %s", filename, exc)
        return []

    # Column-aware path: if the PDF has explicit Retrait/Dépôt columns, use them.
    if bank_rows:
        expenses = []
        for idx, row in enumerate(bank_rows):
            is_dep = row.get("flow") == "deposit"
            amt = _obfuscate_amount(row["amount"]) if is_dep else row["amount"]
            doc = build_expense(
                user_id=user_id,
                source_ref=source_ref,
                line_index=idx,
                date=row.get("date", ""),
                merchant=row.get("merchant", "Unknown"),
                amount=amt,
                currency="CAD",
                category="Other",
                source_type="pdf",
                flow=row.get("flow", "withdrawal"),
                raw_text=full_text,
            )
            errs = validate_expense(doc)
            if not errs:
                expenses.append(doc)
        log.info("PDF %s (columnar) -> %d expenses", filename, len(expenses))
        return expenses

    if not full_text:
        log.warning("No text extracted from PDF %s", filename)
        return []

    raw_rows = watsonx_client.categorize_text(
        text=full_text,
        source_type="pdf",
        source_email_id=source_ref,
    )

    expenses = []
    for idx, row in enumerate(raw_rows):
        doc = build_expense(
            user_id=user_id,
            source_ref=source_ref,
            line_index=idx,
            date=row.get("date", ""),
            merchant=row.get("merchant", "Unknown"),
            amount=(_obfuscate_amount(row.get("amount", 0)) if _is_deposit(row) else row.get("amount", 0)),
            currency=row.get("currency", "CAD"),
            category=row.get("category", "Other"),
            source_type="pdf",
            flow=("deposit" if _is_deposit(row) else "withdrawal"),
            raw_text=full_text,
        )
        errs = validate_expense(doc)
        if errs:
            log.warning("Invalid expense from PDF row %d: %s", idx, errs)
        else:
            expenses.append(doc)

    log.info("PDF %s -> %d expenses", filename, len(expenses))
    return expenses
