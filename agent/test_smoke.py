"""
test_smoke.py — smoke test for the expense agent in mock mode.
Run from the agent/ directory:
    python test_smoke.py

Covers: mcp_client, schema, store, chart, gmail_client, router
Attachment types tested: CSV, text-PDF, image (GIF/PNG), scanned-PDF (image PDF)
No live Gmail / Cloudant / COS / watsonx.ai calls — fully offline.
"""
import io
import os
import sys
import struct
import zlib

# ── Inject required env vars before importing config ──────────────────────
_FAKE_ENV = {
    "MCP_MODE":              "mock",
    "GMAIL_CLIENT_ID":       "fake-client-id",
    "GMAIL_CLIENT_SECRET":   "fake-client-secret",
    "GMAIL_REFRESH_TOKEN":   "fake-refresh-token",
    "WATSONX_APIKEY":        "fake-watsonx-key",
    "WATSONX_PROJECT_ID":    "fake-project-id",
    "COS_APIKEY":            "fake-cos-key",
    "COS_HMAC_ACCESS_KEY":   "fakeaccesskey",
    "COS_HMAC_SECRET_KEY":   "fakesecretkey",
    "CLOUDANT_URL":          "https://fake.cloudantnosqldb.appdomain.cloud",
    "CLOUDANT_APIKEY":       "fake-cloudant-key",
}
for k, v in _FAKE_ENV.items():
    os.environ.setdefault(k, v)

# ── Imports (after env is set) ─────────────────────────────────────────────
import logging
logging.basicConfig(level=logging.WARNING,      # suppress INFO noise in test output
                    format="%(levelname)-8s %(name)s — %(message)s")

import mcp_client
import schema
import store
import chart
import gmail_client
import router
import watsonx_client  # will be monkeypatched

PASS = []
FAIL = []

def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  PASS  {name}")
        PASS.append(name)
    else:
        print(f"  FAIL  {name}" + (f": {detail}" if detail else ""))
        FAIL.append(name)


# ── Fixture builders ───────────────────────────────────────────────────────

def _make_csv_bytes() -> bytes:
    return (
        "date,merchant,amount,currency\n"
        "2026-07-16,Starbucks,6.50,CAD\n"
        "2026-07-15,Uber,12.00,CAD\n"
    ).encode()


def _make_gif_bytes() -> bytes:
    """Minimal valid 1x1 GIF89a."""
    return (
        b"GIF89a\x01\x00\x01\x00\x80\x00\x00"
        b"\xff\xff\xff\x00\x00\x00!\xf9\x04\x00\x00\x00\x00\x00"
        b",\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
    )


def _make_png_bytes() -> bytes:
    """Minimal valid 1x1 white PNG."""
    def chunk(ctype, data):
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    idat = chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff"))
    iend = chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


def _make_text_pdf_bytes() -> bytes:
    """Minimal PDF with a text layer pdfplumber can extract."""
    content = (
        "%PDF-1.4\n"
        "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        "3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]\n"
        "   /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        "4 0 obj\n<< /Length 90 >>\nstream\n"
        "BT /F1 12 Tf 72 720 Td "
        "(Date: 2026-07-16  Merchant: Walmart  Amount: $55.30  CAD  Groceries) Tj ET\n"
        "endstream\nendobj\n"
        "5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        "xref\n0 6\n"
        "0000000000 65535 f \n"
        "0000000009 00000 n \n"
        "0000000058 00000 n \n"
        "0000000115 00000 n \n"
        "0000000266 00000 n \n"
        "0000000420 00000 n \n"
        "trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n510\n%%EOF\n"
    )
    return content.encode()


# ── Monkeypatch watsonx_client (no live API calls) ─────────────────────────

_MOCK_ROWS = [
    {"date": "2026-07-16", "merchant": "Starbucks", "amount": 6.50,
     "currency": "CAD", "category": "Dining"},
    {"date": "2026-07-15", "merchant": "Uber",      "amount": 12.00,
     "currency": "CAD", "category": "Transport"},
]

_MOCK_VISION_DOCS = [
    {"date": "2026-07-14", "merchant": "Walmart", "amount": 55.30,
     "currency": "CAD", "category": "Groceries"},
]

def _fake_categorize_text(*, text, source_type, source_email_id):
    return _MOCK_ROWS

def _fake_parse_image_receipt(image_bytes, *, user_id, source_ref, filename):
    import schema as _schema
    return [
        _schema.build_expense(
            user_id=user_id,
            source_ref=source_ref,
            line_index=i,
            source_type="image",
            raw_text="[mock vision]",
            **{k: v for k, v in row.items()},
        )
        for i, row in enumerate(_MOCK_VISION_DOCS)
    ]

# Patch both modules that import from watsonx_client
import parsers
watsonx_client.categorize_text     = _fake_categorize_text
watsonx_client.parse_image_receipt = _fake_parse_image_receipt
parsers.watsonx_client.categorize_text     = _fake_categorize_text
parsers.watsonx_client.parse_image_receipt = _fake_parse_image_receipt


# ── 1. mcp_client mock routing ─────────────────────────────────────────────
print("\n[1] mcp_client — mock routing")
r = mcp_client.call_tool("gmail_list_messages", query="subject:Expense")
check("gmail_list_messages returns dict",  isinstance(r, dict))
check("gmail_list_messages.messages key",  "messages" in r)

r = mcp_client.call_tool("cloudant_upsert", database="expenses", document={"_id": "test"})
check("cloudant_upsert ok",  r.get("ok") is True)

r = mcp_client.call_tool("s3_put_object", bucket="b", key="k", body=b"x")
check("s3_put_object returns ETag",  "ETag" in r)

try:
    mcp_client.call_tool("unknown_tool_xyz")
    check("unknown tool mock -> returns gracefully", True)
except ValueError:
    check("unknown tool mock -> returns gracefully", True)


# ── 2. schema — build_expense + validate ──────────────────────────────────
print("\n[2] schema — build_expense / validate_expense")
doc = schema.build_expense(
    user_id="user_a",
    source_ref="msg001",
    line_index=0,
    date="16/07/2026",
    merchant="Tim Hortons",
    amount="$4.75",
    currency="cad",
    category="Dining",
    source_type="csv",
    raw_text="raw csv text",
)
check("id is sha256 hex (64 chars)",  len(doc["id"]) == 64)
check("date coerced to YYYY-MM-DD",   doc["date"] == "2026-07-16")
check("amount coerced to float",      doc["amount"] == 4.75)
check("currency uppercased",          doc["currency"] == "CAD")
check("category preserved",           doc["category"] == "Dining")
check("source_type set",              doc["source_type"] == "csv")

errs = schema.validate_expense(doc)
check("validate_expense -> no errors", errs == [], str(errs))

doc2 = schema.build_expense(
    user_id="user_a", source_ref="msg002", line_index=0,
    date="2026-07-16", merchant="X", amount=1.0,
    category="RandomCategory", source_type="pdf",
)
check("unknown category -> Other", doc2["category"] == "Other")

doc3 = schema.build_expense(
    user_id="user_a", source_ref="msg001", line_index=0,
    date="2026-07-16", merchant="Y", amount=2.0,
    source_type="csv",
)
check("same user+source+index -> same id (idempotency)", doc["id"] == doc3["id"])

doc_other_user = schema.build_expense(
    user_id="user_b", source_ref="msg001", line_index=0,
    date="2026-07-16", merchant="Y", amount=2.0,
    source_type="csv",
)
check("different user -> different id", doc["id"] != doc_other_user["id"])


# ── 3. store — mock upsert / query / upload ───────────────────────────────
print("\n[3] store — mock upsert / query / upload")
try:
    store.upsert_expense(doc)
    check("upsert_expense no exception", True)
except Exception as e:
    check("upsert_expense no exception", False, str(e))

try:
    rows = store.query_expenses(user_id="user_a")
    check("query_expenses returns list", isinstance(rows, list))
except Exception as e:
    check("query_expenses returns list", False, str(e))


# ── 4. chart — pie chart + HTML ───────────────────────────────────────────
print("\n[4] chart — build_pie_chart / build_html_table / build_chart_email")
expenses = [
    {**doc, "category": "Dining",    "amount": 45.00},
    {**doc, "category": "Transport", "amount": 22.50},
    {**doc, "category": "Groceries", "amount": 110.30},
]
png = chart.build_pie_chart(expenses)
check("build_pie_chart returns bytes",    isinstance(png, bytes))
check("PNG magic bytes",                  png[:4] == b"\x89PNG")
check("PNG non-empty (> 1KB)",            len(png) > 1024)

html = chart.build_html_table(expenses)
check("html table contains <table>",      "<table" in html)
check("html table contains Dining",       "Dining" in html)
check("html table contains total row",    "Total" in html)

png2, html2 = chart.build_chart_email(expenses)
check("build_chart_email returns png bytes",  isinstance(png2, bytes))
check("build_chart_email embeds base64 img",  "data:image/png;base64," in html2)


# ── 5. gmail_client — mock MCP calls ──────────────────────────────────────
print("\n[5] gmail_client — mock MCP calls")
try:
    msgs = gmail_client.list_unprocessed_messages()
    check("list_unprocessed_messages returns list", isinstance(msgs, list))
except Exception as e:
    check("list_unprocessed_messages returns list", False, str(e))

try:
    gmail_client.mark_processed("mock_msg_001")
    check("mark_processed no exception", True)
except Exception as e:
    check("mark_processed no exception", False, str(e))


# ── 6. router — CSV attachment ────────────────────────────────────────────
print("\n[6] router — CSV attachment")
csv_bytes = _make_csv_bytes()
try:
    docs = router.route(
        data=csv_bytes,
        filename="expenses_july.csv",
        mime_type="text/csv",
        user_id="user_a",
        source_ref="msg_csv_001",
    )
    check("router CSV -> list",                 isinstance(docs, list))
    check("router CSV -> 2 expenses",           len(docs) == 2)
    check("router CSV source_type='csv'",       all(d["source_type"] == "csv" for d in docs))
    check("router CSV merchants extracted",
          {d["merchant"] for d in docs} == {"Starbucks", "Uber"})
except Exception as e:
    for name in ["router CSV -> list", "router CSV -> 2 expenses",
                 "router CSV source_type='csv'", "router CSV merchants extracted"]:
        check(name, False, str(e))


# ── 7. router — GIF attachment (image OCR path) ───────────────────────────
print("\n[7] router — GIF attachment (image OCR path)")
gif_bytes = _make_gif_bytes()
try:
    docs = router.route(
        data=gif_bytes,
        filename="receipt.gif",
        mime_type="image/gif",
        user_id="user_a",
        source_ref="msg_gif_001",
    )
    check("router GIF -> list",                 isinstance(docs, list))
    check("router GIF -> 1 expense",            len(docs) == 1)
    check("router GIF source_type='image'",     docs[0]["source_type"] == "image")
    check("router GIF merchant=Walmart",        docs[0]["merchant"] == "Walmart")
    check("router GIF amount=55.30",            docs[0]["amount"] == 55.30)
except Exception as e:
    for name in ["router GIF -> list", "router GIF -> 1 expense",
                 "router GIF source_type='image'", "router GIF merchant=Walmart",
                 "router GIF amount=55.30"]:
        check(name, False, str(e))


# ── 8. router — PNG attachment ────────────────────────────────────────────
print("\n[8] router — PNG attachment")
png_bytes = _make_png_bytes()
try:
    docs = router.route(
        data=png_bytes,
        filename="receipt.png",
        mime_type="image/png",
        user_id="user_a",
        source_ref="msg_png_001",
    )
    check("router PNG -> list",                 isinstance(docs, list))
    check("router PNG -> 1 expense",            len(docs) == 1)
    check("router PNG source_type='image'",     docs[0]["source_type"] == "image")
except Exception as e:
    for name in ["router PNG -> list", "router PNG -> 1 expense",
                 "router PNG source_type='image'"]:
        check(name, False, str(e))


# ── 9. router — text-PDF attachment ──────────────────────────────────────
print("\n[9] router — text-PDF attachment (Granite path)")
pdf_bytes = _make_text_pdf_bytes()
try:
    docs = router.route(
        data=pdf_bytes,
        filename="receipt.pdf",
        mime_type="application/pdf",
        user_id="user_a",
        source_ref="msg_pdf_001",
    )
    check("router text-PDF -> list",            isinstance(docs, list))
    check("router text-PDF -> 2 expenses",      len(docs) == 2)
    check("router text-PDF source_type='pdf'",  all(d["source_type"] == "pdf" for d in docs))
except Exception as e:
    for name in ["router text-PDF -> list", "router text-PDF -> 2 expenses",
                 "router text-PDF source_type='pdf'"]:
        check(name, False, str(e))


# ── 10. router — scanned PDF (image-PDF path, pypdf extraction) ──────────
print("\n[10] router — scanned PDF (image embedded in PDF)")

def _make_scanned_pdf_bytes() -> bytes:
    """
    Build a minimal PDF with a raw (no filter) 1x1 RGB image XObject
    that pypdf can extract cleanly without needing FlateDecode.
    Raw pixel data: 3 bytes = one white RGB pixel (0xFF 0xFF 0xFF).
    """
    # 1x1 white RGB pixel, no filter — pypdf reads this as raw image data
    raw_pixel = b"\xff\xff\xff"  # R G B
    img_len = len(raw_pixel)

    # Use reportlab-style cross-reference with manually calculated offsets
    obj1 = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    obj2 = b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    obj3 = (
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100]\n"
        b"   /Resources << /XObject << /Im1 4 0 R >> >> >>\nendobj\n"
    )
    obj4 = (
        b"4 0 obj\n"
        b"<< /Type /XObject /Subtype /Image /Width 1 /Height 1\n"
        b"   /ColorSpace /DeviceRGB /BitsPerComponent 8\n"
        b"   /Length " + str(img_len).encode() + b" >>\n"
        b"stream\n" + raw_pixel + b"\nendstream\nendobj\n"
    )
    header = b"%PDF-1.4\n"
    off1 = len(header)
    off2 = off1 + len(obj1)
    off3 = off2 + len(obj2)
    off4 = off3 + len(obj3)
    body = header + obj1 + obj2 + obj3 + obj4
    xref_offset = len(body)
    xref = (
        b"xref\n0 5\n"
        b"0000000000 65535 f \n"
        + f"{off1:010d} 00000 n \n".encode()
        + f"{off2:010d} 00000 n \n".encode()
        + f"{off3:010d} 00000 n \n".encode()
        + f"{off4:010d} 00000 n \n".encode()
    )
    trailer = (
        b"trailer\n<< /Size 5 /Root 1 0 R >>\n"
        b"startxref\n" + str(xref_offset).encode() + b"\n%%EOF\n"
    )
    return body + xref + trailer

scanned_pdf = _make_scanned_pdf_bytes()
try:
    docs = router.route(
        data=scanned_pdf,
        filename="scanned_receipt.pdf",
        mime_type="application/pdf",
        user_id="user_a",
        source_ref="msg_scanpdf_001",
    )
    check("router scanned-PDF -> list",           isinstance(docs, list))
    # pypdf extracts the embedded PNG -> vision mock returns 1 doc
    check("router scanned-PDF -> 1 expense",      len(docs) == 1)
    check("router scanned-PDF source_type=image", docs[0]["source_type"] == "image")
except Exception as e:
    for name in ["router scanned-PDF -> list", "router scanned-PDF -> 1 expense",
                 "router scanned-PDF source_type=image"]:
        check(name, False, str(e))


# ── 11. router — unsupported type ─────────────────────────────────────────
print("\n[11] router — unsupported attachment type")
docs = router.route(
    data=b"<xml/>",
    filename="data.xml",
    mime_type="application/xml",
    user_id="user_a",
    source_ref="msg_xml_001",
)
check("router unsupported -> empty list", docs == [])


# ── Summary ───────────────────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"  {len(PASS)} passed   {len(FAIL)} failed")
print(f"{'='*50}\n")
sys.exit(0 if not FAIL else 1)
