"""
parsers.py — extract expense rows from CSV and text-based PDF attachments.
CSV rows are sent to Granite for normalization/categorization.
Text PDFs are also sent to Granite.
"""
from __future__ import annotations

import io
import logging

import pandas as pd
import pdfplumber

from schema import build_expense, validate_expense
import watsonx_client

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CSV parser
# ---------------------------------------------------------------------------

def parse_csv(data: bytes, *, source_email_id: str, filename: str) -> list[dict]:
    """
    Parse a CSV attachment into a list of canonical expense dicts.
    Sends raw rows to Granite for normalization + categorization.
    """
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
        source_email_id=source_email_id,
    )

    expenses = []
    for idx, row in enumerate(raw_rows):
        doc = build_expense(
            source_email_id=source_email_id,
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

    log.info("CSV %s → %d expenses", filename, len(expenses))
    return expenses


# ---------------------------------------------------------------------------
# Text-PDF parser
# ---------------------------------------------------------------------------

def parse_text_pdf(data: bytes, *, source_email_id: str, filename: str) -> list[dict]:
    """
    Extract text from a text-layer PDF and send to Granite for normalization.
    """
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages_text = [page.extract_text() or "" for page in pdf.pages]
        full_text = "\n\n".join(pages_text).strip()
    except Exception as exc:
        log.error("Failed to extract text from PDF %s: %s", filename, exc)
        return []

    if not full_text:
        log.warning("No text extracted from PDF %s", filename)
        return []

    raw_rows = watsonx_client.categorize_text(
        text=full_text,
        source_type="pdf",
        source_email_id=source_email_id,
    )

    expenses = []
    for idx, row in enumerate(raw_rows):
        doc = build_expense(
            source_email_id=source_email_id,
            line_index=idx,
            date=row.get("date", ""),
            merchant=row.get("merchant", "Unknown"),
            amount=row.get("amount", 0),
            currency=row.get("currency", "CAD"),
            category=row.get("category", "Other"),
            source_type="pdf",
            raw_text=full_text,
        )
        errs = validate_expense(doc)
        if errs:
            log.warning("Invalid expense from PDF row %d: %s", idx, errs)
        else:
            expenses.append(doc)

    log.info("PDF %s → %d expenses", filename, len(expenses))
    return expenses
