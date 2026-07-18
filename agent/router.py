"""
router.py — dispatch an email attachment to the correct parser based on MIME type / extension.
Returns a list of canonical expense dicts (not yet stored).
"""
from __future__ import annotations

import logging
import os
from typing import Callable

log = logging.getLogger(__name__)

# Lazy imports — only load heavy libs when needed
def _parse_csv(data: bytes, user_id: str, source_ref: str, filename: str) -> list[dict]:
    from parsers import parse_csv
    return parse_csv(data, user_id=user_id, source_ref=source_ref, filename=filename)


def _parse_text_pdf(data: bytes, user_id: str, source_ref: str, filename: str) -> list[dict]:
    from parsers import parse_text_pdf
    return parse_text_pdf(data, user_id=user_id, source_ref=source_ref, filename=filename)


def _parse_image(data: bytes, user_id: str, source_ref: str, filename: str) -> list[dict]:
    from watsonx_client import parse_image_receipt
    return parse_image_receipt(data, user_id=user_id, source_ref=source_ref, filename=filename)


def _parse_image_pdf(data: bytes, user_id: str, source_ref: str, filename: str) -> list[dict]:
    """Scanned / image-based PDF: convert first page to image then OCR."""
    from watsonx_client import parse_image_receipt
    image_bytes = _pdf_to_image(data)
    return parse_image_receipt(image_bytes, user_id=user_id, source_ref=source_ref, filename=filename)


def _pdf_to_image(data: bytes) -> bytes:
    """
    Rasterise the first page of a scanned PDF to PNG bytes.
    Uses pypdf (pure-Python) + Pillow — no Poppler binary needed.
    Falls back to sending the raw PDF bytes to the vision model if
    no embedded images can be extracted (very rare edge case).
    """
    import io
    from pypdf import PdfReader
    from PIL import Image

    reader = PdfReader(io.BytesIO(data))
    if not reader.pages:
        return data  # let the vision model handle it as-is

    # Extract the first image embedded in page 0
    page = reader.pages[0]
    images = list(page.images)
    if images:
        # Use the largest image on the first page
        img_obj = max(images, key=lambda x: len(x.data))
        img = Image.open(io.BytesIO(img_obj.data)).convert("RGB")
    else:
        # No embedded images — PDF may be vector; render via page size + blank
        # as a last resort: pass raw bytes straight to the vision model
        return data

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Routing table
# ---------------------------------------------------------------------------

_EXT_MAP: dict[str, Callable | None] = {
    ".csv":  _parse_csv,
    ".png":  _parse_image,
    ".jpg":  _parse_image,
    ".jpeg": _parse_image,
    ".gif":  _parse_image,
    ".webp": _parse_image,
    ".tiff": _parse_image,
    ".tif":  _parse_image,
    ".pdf":  None,  # handled separately — text vs image PDF
}


def route(
    *,
    data: bytes,
    filename: str,
    mime_type: str,
    user_id: str,
    source_ref: str,
) -> list[dict]:
    """
    Dispatch to the right parser. Returns a (possibly empty) list of expense dicts.
    """
    ext = os.path.splitext(filename.lower())[1]

    # CSV
    if ext == ".csv" or mime_type in ("text/csv", "application/csv"):
        log.info("Routing %s -> CSV parser", filename)
        return _parse_csv(data, user_id, source_ref, filename)

    if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".tiff", ".tif") \
            or mime_type.startswith("image/"):
        log.info("Routing %s -> image OCR (Llama vision)", filename)
        return _parse_image(data, user_id, source_ref, filename)

    if ext == ".pdf" or mime_type == "application/pdf":
        if _has_text_layer(data):
            log.info("Routing %s -> text-PDF parser (Granite)", filename)
            return _parse_text_pdf(data, user_id, source_ref, filename)
        log.info("Routing %s -> image-PDF OCR (Llama vision)", filename)
        return _parse_image_pdf(data, user_id, source_ref, filename)

    log.warning("Unsupported attachment type: %s (%s) -- skipping", filename, mime_type)
    return []


def _has_text_layer(pdf_bytes: bytes) -> bool:
    """Return True if pdfplumber can extract at least 20 chars from the first page."""
    try:
        import io
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            if not pdf.pages:
                return False
            text = pdf.pages[0].extract_text() or ""
            return len(text.strip()) >= 20
    except Exception:
        return False
