# Expense Tracker

An AI-powered expense tracker that ingests receipts and bank statements from
**two sources** — a Gmail mailbox poller and a web upload UI — extracts and
categorizes transactions with IBM **watsonx.ai** models, and stores the results
in **IBM Cloudant** (with raw files in **IBM Cloud Object Storage**).

![alt text](image.png)

## Features

- **Two ingest paths, one shared pipeline** — the Gmail poller and the web API
  both call `pipeline.process_file()`, so parsing/storage logic lives in one place.
- **Multi-format parsing**
  - **CSV** → normalized & categorized by the Granite text model.
  - **Images** (`.png/.jpg/.jpeg/.gif/.webp/.tiff`) → OCR + extraction via the
    Llama vision model.
  - **Text PDFs** → column-aware bank-statement parser (see below), Granite fallback.
  - **Scanned/image PDFs** → first page rasterized (pypdf + Pillow) then sent to vision.
- **Column-aware bank statements** — `parsers._parse_bank_statement()` reads the
  ruled table with `pdfplumber.extract_tables()` and maps amounts under the
  **Retrait** column to withdrawals and **Dépôt** to deposits (accent-insensitive).
- **Deposit privacy** — deposit amounts are obfuscated (digits replaced) before
  storage and display, so real income figures are never shown in the demo.
- **Web dashboard** — pie chart by category, "Total spent" / "Total received"
  cards, editable global category list, separate Expenses and Deposits tables,
  and a Reset DB action. JWT-based auth.

## Architecture

```
Gmail poller (agent/main.py) ─┐
                              ├─▶ pipeline.process_file()
Web upload API (web/backend) ─┘        │
                                       ├─▶ store.upload_attachment()  → COS (raw file)
                                       ├─▶ router.route()             → parser / model
                                       │      ├─ parse_csv       → watsonx (Granite)
                                       │      ├─ parse_text_pdf  → columnar / Granite
                                       │      └─ parse_image*    → watsonx (Llama vision)
                                       └─▶ store.upsert_expense()     → Cloudant
```

- **`agent/`** — shared core: `pipeline`, `router`, `parsers`, `watsonx_client`,
  `store` (COS + Cloudant), `schema`, plus the Gmail poller (`main.py`, `gmail_client.py`).
- **`web/backend/`** — FastAPI app: `auth`, `routes_upload`, `routes_expenses`,
  serving the built frontend. Reuses `agent/` modules.
- **`web/frontend/`** — React + Vite SPA (dashboard, upload, login).

## Tech stack

- **AI:** IBM watsonx.ai — Granite (text/CSV), Llama vision (image/scanned PDF)
- **Storage:** IBM Cloudant (expenses), IBM Cloud Object Storage (raw files)
- **Backend:** Python, FastAPI, pdfplumber, pandas, pypdf, Pillow
- **Frontend:** React, Vite, Recharts
- **Auth:** JWT

## Getting started

### 1. Configure secrets
Create `Infra/secrets.env` with your credentials (see `agent/config.py` for the
full list). Required: `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`,
`GMAIL_REFRESH_TOKEN`, `WATSONX_APIKEY`, `WATSONX_PROJECT_ID`, `COS_APIKEY`,
`COS_HMAC_ACCESS_KEY`, `COS_HMAC_SECRET_KEY`, `CLOUDANT_URL`, `CLOUDANT_APIKEY`.
Optional overrides include `WATSONX_URL`, `COS_ENDPOINT`, `COS_BUCKET`,
`CLOUDANT_DB`, `JWT_SECRET`, `MAX_UPLOAD_MB`, `ALLOWED_ORIGINS`.

### 2. Install dependencies
```bash
python -m venv .venv && .venv/Scripts/activate   # Windows
pip install -r agent/requirements.txt -r web/backend/requirements.txt
cd web/frontend && npm install && npm run build   # builds the SPA into dist/
```

### 3. Run the web app
```bash
.venv/Scripts/python -m uvicorn app:app --reload --port 8000 --app-dir web/backend
```
Open http://localhost:8000, register a user, then upload a CSV, image, or PDF.

### 4. Run the Gmail poller (optional)
```bash
.venv/Scripts/python agent/main.py
```
Polls the connected mailbox for receipt attachments and ingests them under
`GMAIL_USER_ID`.

## Testing
```bash
.venv/Scripts/python -m pytest agent/test_smoke.py web/backend/test_web_smoke.py
```

## Deployment
`web/Dockerfile` builds the frontend and serves it from the FastAPI backend in a
single image. Secrets are injected at runtime (e.g. IBM Code Engine
`--env-from-secret`), so nothing sensitive is baked into the image.

## Notes

- Categories are a fixed global list (`agent/config.py`), editable from the
  dashboard; models are prompted to map every transaction to one of them.
- All data is scoped by `user_id` — web users see only their own expenses; Gmail
  ingests are attributed to `GMAIL_USER_ID`.
- Expense IDs are deterministic, so re-ingesting the same file is an idempotent
  upsert rather than a duplicate.
