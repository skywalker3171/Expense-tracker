"""
Rebuild SUBMISSION.pdf to fit in exactly 3 pages using reportlab.
Run from the repo root: python _build_submission_pdf.py
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Preformatted
)
from reportlab.lib import colors

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm

# ── fonts / sizes ──────────────────────────────────────────────────────────────
BASE  = 10.0       # body text
SMALL = 8.5        # table / code
H1    = 14.5
H2    = 11.5
MONO  = "Courier"

styles = getSampleStyleSheet()

def S(name, **kw):
    """Quick style factory."""
    base = styles["Normal"]
    return ParagraphStyle(name, parent=base, **kw)

title_style  = S("Title",   fontSize=H1,   leading=H1*1.45,  spaceAfter=6,  fontName="Helvetica-Bold")
h2_style     = S("H2",      fontSize=H2,   leading=H2*1.5,  spaceBefore=11, spaceAfter=4,  fontName="Helvetica-Bold")
body_style   = S("Body",    fontSize=BASE, leading=BASE*1.6,  spaceAfter=5)
bullet_style = S("Bullet",  fontSize=BASE, leading=BASE*1.6,  leftIndent=12, spaceAfter=3,
                 firstLineIndent=0)
code_style   = S("Code",    fontSize=SMALL, leading=SMALL*1.5, fontName=MONO,
                 leftIndent=8, spaceAfter=6, spaceBefore=4)
footer_style = S("Footer",  fontSize=7, textColor=colors.HexColor("#57606a"),
                 alignment=TA_CENTER)
meta_style   = S("Meta",    fontSize=7, textColor=colors.HexColor("#57606a"), alignment=TA_LEFT)

ACCENT = colors.HexColor("#3b82d4")

def bold(text):
    return f"<b>{text}</b>"

def mono(text):
    return f'<font face="Courier">{text}</font>'

def build():
    story = []

    # ── Title ──────────────────────────────────────────────────────────────────
    story.append(Paragraph("Expense Tracker — watsonx Challenge Submission", title_style))
    story.append(Spacer(1, 2))

    # ── 1. One-line pitch ─────────────────────────────────────────────────────
    story.append(Paragraph("1. One-line pitch", h2_style))
    story.append(Paragraph(
        "A multi-user expense tracker that turns any receipt (image, PDF, or CSV) into categorized, "
        "queryable expenses using an all-IBM stack: <b>watsonx.ai</b> for vision OCR + categorization, "
        "<b>IBM Cloudant</b> for data, and <b>IBM Cloud Object Storage</b> for raw files.",
        body_style))

    # ── 2. Why it matters ─────────────────────────────────────────────────────
    story.append(Paragraph("2. Why it matters", h2_style))
    story.append(Paragraph(
        "Manual expense entry is tedious and error-prone. This project lets a user drop a receipt into "
        "a browser and instantly get structured, categorized expense rows on a dashboard — no manual "
        "typing, no spreadsheets. It began as a single-inbox Gmail agent and was migrated into a real "
        "multi-tenant web product where each user only ever sees their own data.",
        body_style))

    # ── 3. Architecture ───────────────────────────────────────────────────────
    story.append(Paragraph("3. Architecture (all-IBM)", h2_style))

    arch = (
        "Browser (React SPA)\n"
        "   │  upload receipt (image / pdf / csv)  +  JWT auth\n"
        "   ▼\n"
        "FastAPI backend  ──►  pipeline.process_file(user_id, ...)\n"
        "   │                       │\n"
        "   │                       ├─► IBM Cloud Object Storage  (key = {user_id}/{ref}/{name})\n"
        "   │                       │\n"
        "   │                       ├─► watsonx.ai\n"
        "   │                       │      • Llama-3.2-11B-Vision  → OCR image receipts\n"
        "   │                       │      • Granite-3-8B-Instruct → normalize / categorize CSV & PDF\n"
        "   │                       │\n"
        "   │                       └─► IBM Cloudant  (expense docs, tagged with user_id)\n"
        "   ▼\n"
        "Dashboard  ◄── GET /api/expenses | /api/summary | /api/chart.png  (scoped to user_id)"
    )
    story.append(Preformatted(arch, code_style))

    story.append(Paragraph(
        "Two ingest paths share one core: <b>Web upload</b> (browser → /api/upload → pipeline.process_file) "
        "and <b>Gmail poller</b> (cron → run_once() → same core).",
        body_style))

    # IBM services table
    story.append(Spacer(1, 3))
    tdata = [
        [bold("Service"), bold("Role")],
        ["watsonx.ai — Llama-3.2-11B-Vision",   "OCR of image receipts into structured lines"],
        ["watsonx.ai — Granite-3-8B-Instruct",   "Normalize + categorize CSV / text-PDF rows"],
        ["IBM Cloudant",                          "Per-user expense docs (Mango index on user_id, date)"],
        ["IBM Cloud Object Storage",              "Raw uploaded files, namespaced per user"],
        ["IBM Code Engine (planned)",             "Single-container hosting (API + SPA)"],
    ]
    col_w = [(PAGE_W - 2*MARGIN) * f for f in (0.42, 0.58)]
    tbl = Table(
        [[Paragraph(c, S(f"tc{i}", fontSize=SMALL, leading=SMALL*1.3,
                         fontName="Helvetica-Bold" if r == 0 else "Helvetica"))
          for i, c in enumerate(row)]
         for r, row in enumerate(tdata)],
        colWidths=col_w, hAlign="LEFT"
    )
    tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0),  colors.HexColor("#f7f8fa")),
        ("GRID",        (0, 0), (-1, -1), 0.3, colors.HexColor("#e5e7eb")),
        ("TOPPADDING",  (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING",(0,0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(tbl)

    # ── 4. Demo script ────────────────────────────────────────────────────────
    story.append(Paragraph("4. Demo script (5 minutes)", h2_style))
    story.append(Preformatted(
        "cd web/frontend && npm install && npm run build && cd ../..\n"
        "uvicorn app:app --port 8000 --app-dir web/backend\n"
        "# open http://localhost:8000",
        code_style))

    demo_items = [
        ("<b>Register</b> a new account (email + password) → JWT issued, redirected in.",),
        ("<b>Upload</b> a receipt image → watsonx.ai Llama-Vision OCRs it; extracted, categorized rows appear immediately.",),
        ("<b>Upload</b> a CSV / bank-statement PDF → Granite normalizes and categorizes every line.",),
        ("<b>Dashboard</b> shows summary cards, a category pie chart, and the expense table — all for the logged-in user only.",),
        ("<b>Natural-language query:</b> type plain English (e.g. 'groceries from July 1st to 15th') into the search box. "
         + mono("POST /api/query") + " sends it to Granite ("
         + mono("watsonx_client.parse_query()") + "), which returns a structured JSON filter "
         + "(" + mono("categories, date_from, date_to") + ") and a filtered summary + rows.",),
        ("<b>Re-categorization with learning:</b> change a category inline ("
         + mono("PATCH /api/expenses/{id}") + "). The choice is saved as a per-user merchant rule ("
         + mono("store.upsert_category_rule") + "), back-applied to existing expenses, "
         "and auto-applied to future uploads.",),
        ("<b>Multi-tenant proof:</b> register a second user — their expense list is empty / disjoint.",),
        ("<b>Idempotency:</b> re-upload the same file → no duplicate rows (deterministic "
         + mono("sha256(user_id:source_ref:line_index)") + " doc id).",),
    ]
    for i, (text,) in enumerate(demo_items, 1):
        story.append(Paragraph(f"{i}. {text}", bullet_style))

    # ── 5. Deployment status ──────────────────────────────────────────────────
    story.append(Paragraph("5. Deployment status — deploy-ready", h2_style))
    story.append(Paragraph(
        "Container-ready and deploy-ready. A live IBM Code Engine URL is not included because the "
        "available IBM Cloud account is a <b>Lite (free) plan</b> — Code Engine requires Pay-As-You-Go. "
        "Everything needed to deploy is in the repo:",
        body_style))
    for item in [
        mono("web/Dockerfile") + " — multi-stage build (Node builds the SPA; Python serves API + SPA on one port).",
        mono("web/README.md") + " — exact IBM Code Engine commands using " + mono("--build-source") + " (no local Docker daemon required).",
        mono(".dockerignore") + " — keeps secrets and build artefacts out of the image.",
    ]:
        story.append(Paragraph(f"• {item}", bullet_style))

    # ── 6. What's verified ────────────────────────────────────────────────────
    story.append(Paragraph("6. What's verified", h2_style))
    for item in [
        "Register / login issues and accepts JWTs (bcrypt password hashing).",
        "Authenticated upload runs the full watsonx.ai pipeline and returns extracted, categorized expenses.",
        mono("/api/expenses") + ", " + mono("/api/summary") + ", " + mono("/api/chart.png")
            + " return <b>only</b> the caller's data; a second user sees a disjoint, empty set.",
        mono("POST /api/query") + " parses plain English via Granite ("
            + mono("watsonx_client.parse_query()") + ") into a "
            + mono("{categories, date_from, date_to}") + " filter and returns scoped rows.",
        mono("PATCH /api/expenses/{id}") + " updates category, persists a per-user merchant rule, back-applies it, and applies it to future uploads.",
        "Robust LLM JSON parsing: recovers rows even when model output is truncated.",
        "No-Docker parity test: " + mono("python web/backend/test_web_smoke.py") + ".",
    ]:
        story.append(Paragraph(f"• {item}", bullet_style))

    # ── 6b. Security hardening ────────────────────────────────────────────────
    story.append(Paragraph("6b. Security hardening applied", h2_style))
    for item in [
        "<b>No forgeable auth secret</b> — " + mono("JWT_SECRET") + " is required and validated at startup ("
            + mono("agent/config.py") + "): refuses to run if unset, under 16 chars, or a known placeholder.",
        "<b>Safe CORS</b> — removed wildcard-origin + credentials combination ("
            + mono("web/backend/app.py") + "). Auth uses bearer tokens; "
            + mono("allow_credentials=False") + ", methods/headers scoped, "
            + mono("ALLOWED_ORIGINS") + " defaults to deny.",
        "<b>Per-user categories</b> — category list stored per " + mono("user_id") + " ("
            + mono("store.get_categories") + "/" + mono("set_categories") + ", "
            + mono("routes_expenses.py") + "), so one user cannot overwrite the global list.",
    ]:
        story.append(Paragraph(f"• {item}", bullet_style))

    # ── 7. Repo map ───────────────────────────────────────────────────────────
    story.append(Paragraph("7. Repo map", h2_style))
    for item in [
        mono("agent/") + " — shared AI core: router, parsers, watsonx_client, schema, store, chart, pipeline.",
        mono("web/backend/") + " — FastAPI app: app, auth, users, deps, routes_upload, routes_expenses.",
        mono("web/frontend/") + " — React + Vite SPA (Login, Upload, Dashboard).",
        mono("web/Dockerfile") + ", " + mono(".dockerignore") + ", " + mono("web/README.md") + " — deployment.",
        mono("Expense-tracker-web.md") + " — full phased migration plan (W0–W3).",
    ]:
        story.append(Paragraph(f"• {item}", bullet_style))

    # ── Build PDF ─────────────────────────────────────────────────────────────
    def on_page(canvas, doc):
        page_num = doc.page
        total    = 3
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#57606a"))
        canvas.drawString(MARGIN, 10*mm,  "SUBMISSION.md — 2026-07-20")
        canvas.drawRightString(PAGE_W - MARGIN, 10*mm, f"{page_num} / {total}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        "SUBMISSION.pdf",
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=14*mm,   bottomMargin=16*mm,
    )
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    print("Done — SUBMISSION.pdf written.")

if __name__ == "__main__":
    build()
