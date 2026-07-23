# Software Design Document (SDD)
## WatsonX Expense Tracker

**Version:** 1.0  
**Status:** Released  
**Classification:** Internal / Submission  

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [System Overview](#2-system-overview)
3. [Architecture](#3-architecture)
   - 3.1 [High-Level Architecture](#31-high-level-architecture)
   - 3.2 [Component Diagram](#32-component-diagram)
   - 3.3 [Ingest Paths](#33-ingest-paths)
4. [Technology Stack](#4-technology-stack)
5. [Repository Structure](#5-repository-structure)
6. [Data Model](#6-data-model)
   - 6.1 [Expense Document](#61-expense-document)
   - 6.2 [User Document](#62-user-document)
   - 6.3 [Category Rule Document](#63-category-rule-document)
   - 6.4 [Settings Document](#64-settings-document)
   - 6.5 [Document ID Strategy](#65-document-id-strategy)
7. [Agent Core](#7-agent-core)
   - 7.1 [config.py — Environment & Secrets](#71-configpy--environment--secrets)
   - 7.2 [schema.py — Data Contract](#72-schemapy--data-contract)
   - 7.3 [store.py — Persistence Layer](#73-storepy--persistence-layer)
   - 7.4 [pipeline.py — Processing Orchestrator](#74-pipelinepy--processing-orchestrator)
   - 7.5 [router.py — File-Type Dispatcher](#75-routerpy--file-type-dispatcher)
   - 7.6 [parsers.py — Format Parsers](#76-parserspy--format-parsers)
   - 7.7 [watsonx_client.py — AI Integration](#77-watsonx_clientpy--ai-integration)
   - 7.8 [chart.py — Visualization](#78-chartpy--visualization)
   - 7.9 [gmail_client.py — Gmail Integration](#79-gmail_clientpy--gmail-integration)
   - 7.10 [mcp_client.py — MCP Server Manager](#710-mcp_clientpy--mcp-server-manager)
   - 7.11 [main.py — Gmail Poller Entrypoint](#711-mainpy--gmail-poller-entrypoint)
8. [Web Backend](#8-web-backend)
   - 8.1 [app.py — FastAPI Application](#81-apppy--fastapi-application)
   - 8.2 [auth.py — Authentication Routes](#82-authpy--authentication-routes)
   - 8.3 [deps.py — JWT Helpers](#83-depspy--jwt-helpers)
   - 8.4 [users.py — User Store](#84-userspy--user-store)
   - 8.5 [routes_upload.py — File Upload](#85-routes_uploadpy--file-upload)
   - 8.6 [routes_expenses.py — Expense API](#86-routes_expensespy--expense-api)
9. [Web Frontend](#9-web-frontend)
   - 9.1 [Entry Point & Routing](#91-entry-point--routing)
   - 9.2 [auth.jsx — Auth Context](#92-authjsx--auth-context)
   - 9.3 [api.js — HTTP Client](#93-apijs--http-client)
   - 9.4 [Login Page](#94-login-page)
   - 9.5 [Upload Page](#95-upload-page)
   - 9.6 [Dashboard Page](#96-dashboard-page)
10. [Security Design](#10-security-design)
11. [AI Model Usage](#11-ai-model-usage)
    - 11.1 [Llama 3.2 Vision — Receipt OCR](#111-llama-32-vision--receipt-ocr)
    - 11.2 [Granite 3 — Text Normalization & NL Query](#112-granite-3--text-normalization--nl-query)
    - 11.3 [Prompt Contracts](#113-prompt-contracts)
12. [Category Learning Loop](#12-category-learning-loop)
13. [Deposit Privacy](#13-deposit-privacy)
14. [API Reference](#14-api-reference)
    - 14.1 [Auth Endpoints](#141-auth-endpoints)
    - 14.2 [Upload Endpoint](#142-upload-endpoint)
    - 14.3 [Expense Endpoints](#143-expense-endpoints)
15. [Configuration Reference](#15-configuration-reference)
16. [Deployment](#16-deployment)
    - 16.1 [Docker Build](#161-docker-build)
    - 16.2 [IBM Code Engine](#162-ibm-code-engine)
    - 16.3 [Local Development](#163-local-development)
17. [Testing](#17-testing)
18. [Non-Functional Requirements](#18-non-functional-requirements)
19. [Known Constraints & Design Decisions](#19-known-constraints--design-decisions)

---

## 1. Introduction

### 1.1 Purpose

This Software Design Document (SDD) describes the complete design of the **WatsonX Expense Tracker**, a multi-tenant SaaS application that automatically ingests, categorizes, and stores expenses from receipts in any format — photos, PDFs, CSV bank exports, and Gmail attachments.

This document is intended to be sufficient to fully reconstruct the system from scratch.

### 1.2 Problem Statement

Users accumulate receipts in incompatible formats: smartphone photos, scanned PDFs, CSV bank exports, emailed attachments. Manual entry into a ledger is error-prone and time-consuming. There is no single tool that accepts all formats, applies AI categorization, and learns from corrections.

### 1.3 Solution Summary

Drop any receipt → AI pipeline extracts and categorizes it → searchable, structured record.

- **Any format**: images, PDFs (text or scanned), CSV bank statements
- **Two ingest paths**: web upload UI and Gmail attachment poller — sharing one pipeline
- **Category learning**: corrections teach the system per-user merchant rules
- **Deposit privacy**: income amounts are obfuscated so the dashboard is shareable
- **100% IBM stack**: watsonx.ai, Cloudant, Cloud Object Storage, Code Engine

### 1.4 Scope

The system covers:
- User registration and login
- File upload and AI-driven expense extraction
- Gmail polling and automated ingestion
- Category management and merchant-rule learning
- Natural-language expense querying
- Expense dashboard with charts
- Deployment to IBM Cloud Code Engine

---

## 2. System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                         User Interface                               │
│         React SPA (Vite + Tailwind CSS + Recharts)                   │
│    Login │ Upload │ Dashboard │ Categories │ NL Query                │
└──────────────────────────┬───────────────────────────────────────────┘
                           │ HTTPS / Bearer JWT
┌──────────────────────────▼───────────────────────────────────────────┐
│                   Web Backend (FastAPI)                              │
│  /api/auth  │  /api/upload  │  /api/expenses  │  /api/query         │
│  JWT auth   │  Size limit   │  CRUD + summary │  NL → filter        │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────────┐
│                      Agent Core (Python)                             │
│                                                                      │
│  pipeline.py → router.py → parsers.py → watsonx_client.py           │
│  store.py (Cloudant + COS)   schema.py   chart.py                   │
└──────────┬──────────────────────┬────────────────────────────────────┘
           │                      │
           ▼                      ▼
    Gmail Poller            IBM Cloud Services
    (main.py)               Cloudant · COS · watsonx.ai
```

---

## 3. Architecture

### 3.1 High-Level Architecture

The application is a **monorepo** with three logical layers:

| Layer | Location | Technology |
|---|---|---|
| Frontend SPA | `web/frontend/` | React 18, Vite 5, Tailwind CSS 4, Recharts |
| Web Backend | `web/backend/` | Python 3.12, FastAPI, Uvicorn |
| Agent Core | `agent/` | Python 3.12, shared by web backend and Gmail poller |

In **production**, all three are bundled into a single Docker image. The Vite build output (`dist/`) is copied into the image, and FastAPI serves both the API and the static SPA from port 8080.

In **local development**, the frontend runs separately on port 5173 (Vite dev server) and proxies `/api` requests to the backend on port 8000.

### 3.2 Component Diagram

```
agent/
├── config.py          # All environment-variable secrets
├── schema.py          # Expense contract, ID generation, coercions
├── store.py           # Cloudant + COS read/write
├── pipeline.py        # Orchestrates parse → normalize → store
├── router.py          # Dispatches file to correct parser
├── parsers.py         # CSV, text-PDF, image-PDF, OCR parsers
├── watsonx_client.py  # Llama Vision + Granite REST API
├── chart.py           # matplotlib pie chart + HTML table
├── gmail_client.py    # Gmail MCP wrapper
├── mcp_client.py      # MCP subprocess manager (JSON-RPC)
└── main.py            # Gmail poller entrypoint

web/
├── backend/
│   ├── app.py               # FastAPI app factory, routes, SPA fallback
│   ├── auth.py              # /auth/register, /auth/login, /auth/me
│   ├── deps.py              # JWT issue/decode, current_user dependency
│   ├── users.py             # User CRUD in Cloudant
│   ├── routes_upload.py     # POST /upload
│   └── routes_expenses.py   # GET /expenses, /summary, /query, PATCH /:id
├── frontend/
│   ├── src/
│   │   ├── main.jsx         # React entry, BrowserRouter, AuthProvider
│   │   ├── App.jsx          # Route layout, RequireAuth, NavBar
│   │   ├── auth.jsx         # AuthContext, useAuth hook
│   │   ├── api.js           # Fetch wrapper with JWT bearer token
│   │   ├── styles.css       # Tailwind entry point + body color
│   │   └── pages/
│   │       ├── Login.jsx    # Login / Register toggle
│   │       ├── Upload.jsx   # Drag-and-drop upload, result table
│   │       └── Dashboard.jsx# Stats, bar chart, NL query, recategorize
│   ├── package.json
│   └── vite.config.js
└── Dockerfile               # Multi-stage: Node build → Python runtime
```

### 3.3 Ingest Paths

The system has two ingest paths that share a single `pipeline.process_file()` entry point:

```
Web Upload Path
───────────────
Browser  →  POST /api/upload (multipart)  →  routes_upload.py
         →  pipeline.process_file(bytes, filename, user_id, source_ref=uuid)
         →  [router → parsers → watsonx → store]
         →  {count, expenses} response

Gmail Poller Path
─────────────────
Cron/Loop  →  main.py  →  gmail_client.list_unprocessed_messages()
           →  gmail_client.get_attachment()  →  pipeline.process_file(bytes, filename, GMAIL_USER_ID)
           →  [router → parsers → watsonx → store]
           →  gmail_client.mark_processed()
```

Both paths converge at `pipeline.process_file(file_bytes, filename, user_id, source_ref)`. The only difference is how the file bytes and user context are supplied.

---

## 4. Technology Stack

| Category | Technology | Version / Notes |
|---|---|---|
| Frontend framework | React | 18.3.x |
| Frontend build | Vite | 5.4.x |
| Frontend CSS | Tailwind CSS | 4.1.x (Vite plugin) |
| Frontend charts | Recharts | 2.12.x |
| Frontend routing | React Router DOM | 6.26.x |
| Backend framework | FastAPI | 0.115.0 |
| ASGI server | Uvicorn | 0.30.6 (standard extras) |
| Auth tokens | PyJWT | 2.9.0 (HS256) |
| Password hashing | bcrypt | ≥ 4.2 |
| AI — Vision OCR | watsonx.ai Llama 3.2 11B Vision | `meta-llama/llama-3-2-11b-vision-instruct` |
| AI — Text / NL | watsonx.ai Granite 3 8B Instruct | `ibm/granite-3-8b-instruct` |
| AI SDK | ibm-watsonx-ai | ≥ 1.1.2 |
| Database | IBM Cloudant | REST (Mango queries) |
| Object storage | IBM Cloud Object Storage | boto3 + HMAC credentials |
| PDF text extraction | pdfplumber | ≥ 0.11.0 |
| PDF parsing (meta) | pypdf | ≥ 4.0.0 |
| Image rasterization | Pillow | ≥ 10.3.0 |
| Data wrangling | pandas | ≥ 2.2.0 |
| Charts (server-side) | matplotlib | ≥ 3.9.0 |
| Environment secrets | python-dotenv | ≥ 1.0.0 |
| HTTP client | requests | ≥ 2.32.0 |
| File upload (FastAPI) | python-multipart | 0.0.9 |
| Container base | python:3.12-slim + node:20-alpine | Multi-stage Docker |
| Cloud runtime | IBM Code Engine | Managed containers |

---

## 5. Repository Structure

```
WatsonX/
├── agent/                      # Shared AI + storage core
│   ├── config.py
│   ├── schema.py
│   ├── store.py
│   ├── pipeline.py
│   ├── router.py
│   ├── parsers.py
│   ├── watsonx_client.py
│   ├── chart.py
│   ├── gmail_client.py
│   ├── mcp_client.py
│   ├── main.py
│   ├── requirements.txt
│   └── test_smoke.py
├── web/
│   ├── backend/
│   │   ├── app.py
│   │   ├── auth.py
│   │   ├── deps.py
│   │   ├── users.py
│   │   ├── routes_upload.py
│   │   ├── routes_expenses.py
│   │   ├── requirements.txt
│   │   └── test_web_smoke.py
│   ├── frontend/
│   │   ├── src/
│   │   │   ├── main.jsx
│   │   │   ├── App.jsx
│   │   │   ├── auth.jsx
│   │   │   ├── api.js
│   │   │   ├── styles.css
│   │   │   └── pages/
│   │   │       ├── Login.jsx
│   │   │       ├── Upload.jsx
│   │   │       └── Dashboard.jsx
│   │   ├── index.html
│   │   ├── package.json
│   │   └── vite.config.js
│   └── Dockerfile
├── Infra/
│   └── secrets.env             # Runtime secrets (never committed)
├── README.md
├── SUBMISSION.md
└── SDD.md
```

**Path injection**: `web/backend/app.py` inserts `agent/` into `sys.path` at startup so the backend can `import pipeline`, `import store`, etc. without packaging. Tests mirror this pattern.

---

## 6. Data Model

All persistent data lives in a single IBM Cloudant database. Documents are differentiated by their `type` field. There are no joins; all queries use user-scoped Mango filters.

### 6.1 Expense Document

```json
{
  "_id":            "<sha256 hex — 64 chars>",
  "_rev":           "<cloudant revision>",
  "type":           "expense",
  "user_id":        "<uuid>",
  "date":           "YYYY-MM-DD",
  "merchant":       "coffee shop name",
  "amount":         12.50,
  "currency":       "CAD",
  "category":       "Dining",
  "source_type":    "image | csv | pdf",
  "flow":           "withdrawal | deposit",
  "source_ref":     "<upload uuid or gmail message id>",
  "source_email_id":"<same as source_ref for Gmail path>",
  "raw_text":       "<full OCR or parsed text>",
  "created_at":     "2024-01-15T10:30:00Z"
}
```

**Constraints**:
- `amount` ≥ 0 (always positive; direction is encoded in `flow`)
- `flow` defaults to `"withdrawal"` for all non-deposit rows
- `source_type` must be one of `pdf`, `image`, `csv`
- `category` must be in the user's category list (or system defaults); defaults to `"Other"`

### 6.2 User Document

```json
{
  "_id":           "user:<lowercase-email>",
  "type":          "user",
  "email":         "alice@example.com",
  "password_hash": "<bcrypt hash>",
  "user_id":       "<uuid4>",
  "created_at":    "2024-01-15T10:00:00Z"
}
```

### 6.3 Category Rule Document

Created or updated whenever a user manually recategorizes an expense. Used to auto-apply the correct category to future uploads from the same merchant.

```json
{
  "_id":          "catrule:<user_id>:<merchant_key>",
  "type":         "category_rule",
  "user_id":      "<uuid>",
  "merchant_key": "<normalized merchant string>",
  "category":     "Dining",
  "updated_at":   "2024-01-15T11:00:00Z"
}
```

`merchant_key` is produced by `schema.normalize_merchant()`: lowercased, stripped of digits and common noise words, trimmed.

### 6.4 Settings Document

Stores per-user custom category lists.

```json
{
  "_id":        "settings:categories:<user_id>",
  "type":       "settings",
  "user_id":    "<uuid>",
  "categories": ["Groceries", "Dining", "Transport", "Utilities",
                 "Housing", "Health", "Entertainment", "Shopping",
                 "Travel", "Other"]
}
```

If no settings document exists for a user, `store.get_categories()` returns the system default list defined in `config.py`.

### 6.5 Document ID Strategy

Expense IDs are deterministic and content-addressed:

```python
# agent/schema.py
def make_id(user_id: str, source_ref: str, line_index: int) -> str:
    key = f"{user_id}:{source_ref}:{line_index}"
    return hashlib.sha256(key.encode()).hexdigest()
```

**Effect**: uploading the same file twice produces identical IDs → Cloudant upsert updates the existing document rather than creating a duplicate. This idempotency guarantee is critical for resilient re-ingest.

> ⚠️ Do not change the tuple order or field semantics of `make_id()`. Doing so breaks idempotent re-uploads for existing data.

---

## 7. Agent Core

The `agent/` directory is a set of plain Python modules (no package `__init__.py`). The backend imports them after inserting `agent/` into `sys.path`.

### 7.1 `config.py` — Environment & Secrets

Loads all secrets from environment variables via `python-dotenv`. Fails hard at import time if `JWT_SECRET` is missing or shorter than 16 characters.

**Required environment variables:**

| Variable | Purpose |
|---|---|
| `WATSONX_APIKEY` | watsonx.ai IAM API key |
| `WATSONX_PROJECT_ID` | watsonx.ai project UUID |
| `WATSONX_URL` | watsonx.ai endpoint (e.g. `https://us-south.ml.cloud.ibm.com`) |
| `COS_APIKEY` | Cloud Object Storage IAM key |
| `COS_ENDPOINT` | COS endpoint URL |
| `COS_HMAC_ACCESS_KEY` | COS HMAC access key (for boto3) |
| `COS_HMAC_SECRET_KEY` | COS HMAC secret key (for boto3) |
| `COS_BUCKET` | COS bucket name |
| `CLOUDANT_URL` | Cloudant instance URL |
| `CLOUDANT_APIKEY` | Cloudant IAM key |
| `CLOUDANT_DB` | Cloudant database name |
| `JWT_SECRET` | HS256 signing secret (≥ 16 chars) |
| `GMAIL_CLIENT_ID` | OAuth2 client ID (Gmail poller only) |
| `GMAIL_CLIENT_SECRET` | OAuth2 client secret (Gmail poller only) |
| `GMAIL_REFRESH_TOKEN` | OAuth2 refresh token (Gmail poller only) |
| `GMAIL_USER_ID` | Gmail account to poll (Gmail poller only) |

**Optional variables:**

| Variable | Default | Purpose |
|---|---|---|
| `ALLOWED_ORIGINS` | `http://localhost:5173` | CORS allow-list (comma-separated) |
| `MAX_UPLOAD_MB` | `20` | Maximum upload file size |

**Default categories** (defined in `config.py`):
```
Groceries, Dining, Transport, Utilities, Housing,
Health, Entertainment, Shopping, Travel, Other
```

### 7.2 `schema.py` — Data Contract

Provides four public functions:

#### `make_id(user_id, source_ref, line_index) → str`
SHA-256 hex of `"{user_id}:{source_ref}:{line_index}"`.

#### `normalize_merchant(merchant: str) → str`
Produces a stable key for category rule matching:
1. Lowercase
2. Remove all digit characters
3. Remove common noise words (e.g., "inc", "ltd", "the")
4. Strip and collapse whitespace

> This exact normalization must be used in **both** `pipeline.py` (rule lookup) and `routes_expenses.py` (rule save). Any drift breaks the learning loop.

#### `build_expense(row, user_id, source_ref, line_index, source_type) → dict`
Constructs a validated expense document:
- Calls `make_id()` for `_id`
- Coerces `date` (supports ISO, DD/MM/YYYY, MM/DD/YYYY, French/English month names)
- Coerces `amount` (strips currency symbols `$`, `€`, `£`, commas)
- Coerces `currency` (uppercase, defaults `"CAD"`)
- Coerces `category` against allowed list (defaults `"Other"`)
- Sets `flow` to `"deposit"` or `"withdrawal"`

#### `validate_expense(expense: dict) → list[str]`
Returns a list of validation error strings. Empty list means valid.
- Checks `date`, `merchant`, `amount`, `source_type` are present and well-formed
- Checks `amount >= 0`
- Checks `source_type in {"pdf", "image", "csv"}`

### 7.3 `store.py` — Persistence Layer

All Cloudant operations use direct REST calls (not the official SDK) to avoid dependencies. IAM access tokens are cached and refreshed with a 60-second buffer before expiry.

#### Functions

| Function | Description |
|---|---|
| `upload_attachment(user_id, source_ref, file_bytes, filename)` | Store raw file to COS under key `{user_id}/{source_ref}/{filename}` |
| `upsert_expense(expense)` | PUT to Cloudant with `_rev` if the document already exists |
| `query_expenses(user_id, date_from, date_to, categories)` | Mango selector `{user_id: …, date: {$gte:…}}` |
| `get_expense(expense_id, user_id)` | Fetch by `_id`, verify `user_id` matches |
| `get_categories(user_id)` | Return user settings doc categories, or defaults |
| `set_categories(user_id, categories)` | Upsert settings doc |
| `get_category_rules(user_id)` | All `type:"category_rule"` docs for user |
| `upsert_category_rule(user_id, merchant_key, category)` | Save merchant→category mapping |
| `delete_user_expenses(user_id)` | Bulk delete all expense docs for user (demo reset) |

**Error behavior**: write failures log then raise; read failures (e.g., `query_expenses`) log then return `[]` to keep the UI functional.

### 7.4 `pipeline.py` — Processing Orchestrator

Single public function:

```python
def process_file(
    file_bytes: bytes,
    filename: str,
    user_id: str,
    source_ref: str | None = None
) -> list[dict]
```

**Steps:**
1. Generate `source_ref` (UUID) if not provided
2. `store.upload_attachment(user_id, source_ref, file_bytes, filename)` — stores raw file
3. `router.route(file_bytes, filename)` → list of raw row dicts
4. Load `store.get_category_rules(user_id)` → merchant key → category map
5. For each row:
   a. `schema.build_expense(row, user_id, source_ref, i, source_type)`
   b. Check `normalize_merchant(expense["merchant"])` against rules; override `category` if match found
   c. `store.upsert_expense(expense)`
6. Return list of stored expenses

### 7.5 `router.py` — File-Type Dispatcher

```python
def route(file_bytes: bytes, filename: str) -> list[dict]
```

Dispatch logic:

| Condition | Parser called | `source_type` |
|---|---|---|
| Extension `.csv` | `parsers.parse_csv()` | `csv` |
| Extension in `{.png, .jpg, .jpeg, .gif, .webp, .tiff, .tif}` | `watsonx_client.parse_image_receipt()` | `image` |
| Extension `.pdf` AND `_has_text_layer()` returns True | `parsers.parse_text_pdf()` | `pdf` |
| Extension `.pdf` AND no text layer | `_pdf_to_image()` then `watsonx_client.parse_image_receipt()` | `image` |

#### `_has_text_layer(file_bytes) → bool`
Uses pdfplumber to extract text from page 1. Returns `True` if extracted text has ≥ 20 characters.

#### `_pdf_to_image(file_bytes) → bytes`
Uses pypdf to rasterize the first page to PNG bytes using Pillow. The resulting PNG is then treated as a scanned image.

Heavy library imports (`pdfplumber`, `pandas`, `ibm_watsonx_ai`) are done lazily inside functions to reduce startup time.

### 7.6 `parsers.py` — Format Parsers

#### `parse_csv(file_bytes) → list[dict]`
1. Load bytes into pandas DataFrame
2. Concatenate all rows into a text block
3. Call `watsonx_client.categorize_text(text)` → normalized rows
4. Return list of row dicts

#### `parse_text_pdf(file_bytes) → list[dict]`
1. Try `_parse_bank_statement(file_bytes)` first (structured column extraction)
2. If no rows returned, extract all text with pdfplumber and call `watsonx_client.categorize_text(text)`

#### `_parse_bank_statement(file_bytes) → list[dict]`
Uses pdfplumber table extraction to detect Retrait (withdrawal) / Dépôt (deposit) column layout common in French-Canadian bank statements. Maps columns to expense fields directly, without AI, for maximum reliability.

#### `_obfuscate_amount(amount: float) → float`
Replaces every integer digit in the formatted amount string with `1`, then parses back to float. Example: `45.78 → 11.11`. Used for deposit privacy.

#### `_is_deposit(row: dict) → bool`
Returns `True` if:
- `row["flow"] == "deposit"` (explicit), OR
- `row["merchant"]` or `row["raw_text"]` contains keywords: `dépôt`, `depot`, `deposit`, `DI` (transaction code)

### 7.7 `watsonx_client.py` — AI Integration

All AI calls use the watsonx.ai REST endpoint `POST /ml/v1/text/chat` with `temperature=0.0` (deterministic output). IAM tokens are cached with a 60-second safety buffer.

#### `parse_image_receipt(image_bytes) → list[dict]`
- Model: `meta-llama/llama-3-2-11b-vision-instruct`
- Input: base64-encoded image
- System prompt: instructs the model to return a JSON array of expense rows with fields `date, merchant, amount, currency, category, flow`
- Defensive parsing via `_extract_json()` handles truncated LLM output

#### `categorize_text(text: str) → list[dict]`
- Model: `ibm/granite-3-8b-instruct`
- Input: raw text from CSV or PDF
- System prompt: instructs the model to normalize rows and return a JSON array including the `flow` field (`withdrawal` / `deposit`)

#### `parse_query(query: str) → dict`
- Model: `ibm/granite-3-8b-instruct`
- Input: natural-language query string (e.g., "show me dining expenses last month")
- Output: `{"categories": ["Dining"], "date_from": "2024-01-01", "date_to": "2024-01-31"}`

#### `_extract_json(text: str) → any`
Defensive JSON parser:
1. Try `json.loads(text)` directly
2. Try extracting first `[…]` or `{…}` block
3. Try repairing truncated arrays by closing with `]`
4. Return `[]` as last resort

### 7.8 `chart.py` — Visualization

Used by the Gmail chart-request handler. The web frontend generates its own charts using Recharts client-side.

| Function | Description |
|---|---|
| `build_pie_chart(expenses) → bytes` | matplotlib pie chart PNG, one slice per category |
| `build_html_table(expenses) → str` | HTML `<table>` of expenses with category totals row |
| `build_chart_email(expenses) → str` | Full HTML email embedding the pie chart as a `data:` URI |

### 7.9 `gmail_client.py` — Gmail Integration

Thin wrapper over Gmail MCP tools exposed via `mcp_client`.

| Function | Description |
|---|---|
| `list_unprocessed_messages()` | Search unread emails with "Expense" or "Chart" in subject; exclude "Processed" label |
| `get_message(msg_id)` | Fetch full message with headers and attachment metadata |
| `get_attachment(msg_id, attachment_id, filename)` | Download attachment to temp file, read bytes, delete temp file |
| `mark_processed(msg_id)` | Apply "Processed" label and mark as read |
| `send_reply(to, subject, html_body, png_bytes)` | Send HTML email with optional PNG attachment |

### 7.10 `mcp_client.py` — MCP Server Manager

Manages persistent MCP server subprocesses (one per server key). Communicates via JSON-RPC 2.0 over stdio.

**MCP servers managed:**
- **Gmail MCP**: exposes Gmail read/write tools
- **Cloudant MCP**: exposes Cloudant document CRUD tools
- **S3 MCP**: exposes COS object storage tools

**Implementation details:**
- Subprocess is started lazily on first tool call and reused
- A background reader thread collects responses into a dict keyed by request ID
- Tool → server routing: explicit maps for Gmail and Cloudant tools; prefix match for S3 tools
- Mock mode: when `MCP_MOCK=1`, returns empty responses for use in tests

### 7.11 `main.py` — Gmail Poller Entrypoint

Two run modes:

| Mode | Command | Behavior |
|---|---|---|
| One-shot | `python main.py` | Process all unread expense/chart emails, then exit |
| Loop | `python main.py --loop` | Run one-shot every 60 seconds indefinitely |

**`_process_message(msg_id)`**:
1. Fetch message headers and attachments
2. For each attachment: `gmail_client.get_attachment()` → `pipeline.process_file(bytes, filename, GMAIL_USER_ID)`
3. `gmail_client.mark_processed(msg_id)`

**`_handle_chart_request(msg_id, sender)`**:
1. Query all expenses for `GMAIL_USER_ID`
2. `chart.build_pie_chart()` + `chart.build_html_table()`
3. `gmail_client.send_reply(sender, subject, html, png_bytes)`
4. `gmail_client.mark_processed(msg_id)`

---

## 8. Web Backend

`web/backend/` is a FastAPI application. It adds `agent/` to `sys.path` at startup to access the agent core directly.

### 8.1 `app.py` — FastAPI Application

**Startup sequence:**
1. Load `Infra/secrets.env` via `python-dotenv` (file presence optional; env vars may already be set)
2. Import agent modules (triggers `config.py` validation — fails fast if secrets are missing)
3. Configure CORS middleware with origins from `config.ALLOWED_ORIGINS`
4. Mount routers
5. If `web/frontend/dist/` exists: mount as `StaticFiles`, add SPA fallback route returning `index.html`

**Routes:**

| Prefix | Router module | Purpose |
|---|---|---|
| `/api/auth` | `auth.py` | Register, login, token validation |
| `/api` | `routes_upload.py` | File upload |
| `/api` | `routes_expenses.py` | Expense CRUD, summary, query |
| `/api/health` | inline | Health check, returns `{"status": "ok"}` |
| `/{full_path:path}` | inline | SPA fallback — serves `index.html` |

### 8.2 `auth.py` — Authentication Routes

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/api/auth/register` | None | Create user, return JWT |
| `POST` | `/api/auth/login` | None | Verify credentials, return JWT |
| `GET` | `/api/auth/me` | Bearer JWT | Return `{email, user_id}` |

**Register flow:**
1. Check email not already taken (query Cloudant for `user:<email>`)
2. `users.create_user(email, password)` → bcrypt hash, UUID user_id, store doc
3. `deps.issue_token(user_id)` → return `{access_token, token_type}`

**Login flow:**
1. `users.verify_credentials(email, password)` → fetch doc, bcrypt verify
2. `deps.issue_token(user_id)` → return `{access_token, token_type}`

### 8.3 `deps.py` — JWT Helpers

```python
def issue_token(user_id: str) -> str:
    # HS256, 7-day TTL
    payload = {"sub": user_id, "exp": utcnow() + timedelta(days=7)}
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")

async def current_user(token: HTTPAuthorizationCredentials) -> str:
    # Raises HTTP 401 if missing or invalid
    payload = jwt.decode(token.credentials, config.JWT_SECRET, algorithms=["HS256"])
    return payload["sub"]  # user_id
```

Every protected route declares `user_id: str = Depends(current_user)` to enforce authentication and provide the scoped user identity.

### 8.4 `users.py` — User Store

All user records are stored in Cloudant with `_id = "user:<email>"`.

```python
def create_user(email: str, password: str) -> dict
def verify_credentials(email: str, password: str) -> str  # returns user_id
def get_user(email: str) -> dict | None
```

Password is bcrypt-hashed before storage. Verification calls `bcrypt.checkpw()`.

### 8.5 `routes_upload.py` — File Upload

```
POST /api/upload
Content-Type: multipart/form-data
Authorization: Bearer <token>
Body: file=<binary>
```

**Steps:**
1. Check `len(file_bytes) <= config.MAX_UPLOAD_MB * 1024 * 1024`; return HTTP 413 if exceeded
2. Generate `source_ref = str(uuid.uuid4())`
3. Call `pipeline.process_file(file_bytes, filename, user_id, source_ref)`
4. Return `{"count": N, "expenses": [...]}`

### 8.6 `routes_expenses.py` — Expense API

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/expenses` | List expenses and deposits (two arrays) |
| `GET` | `/api/summary` | Count + total per category |
| `GET` | `/api/categories` | User's category list |
| `PUT` | `/api/categories` | Replace user's category list |
| `PATCH` | `/api/expenses/{id}` | Recategorize expense |
| `POST` | `/api/query` | NL query → filtered expense list |
| `GET` | `/api/chart.png` | Server-side pie chart PNG |
| `POST` | `/api/reset` | Delete all user expenses (demo) |

**Recategorize flow** (`PATCH /api/expenses/{id}`):
1. `store.get_expense(id, user_id)` — verifies ownership
2. Update `category` field, `store.upsert_expense()`
3. `store.upsert_category_rule(user_id, normalize_merchant(expense["merchant"]), new_category)` — save rule
4. Back-apply: `store.query_expenses(user_id)` → for each expense with same merchant key → update category and upsert

**NL Query flow** (`POST /api/query`):
1. `watsonx_client.parse_query(query_text)` → `{categories, date_from, date_to}`
2. `store.query_expenses(user_id, date_from, date_to)` → raw list
3. `_apply_filter(expenses, categories)` → filtered list
4. Return filtered expenses

**`_apply_filter(expenses, categories)`**: Returns expenses whose `category` is in the provided list (case-insensitive). If categories list is empty, no category filter is applied.

---

## 9. Web Frontend

Single-page React application built with Vite. All state is local (React hooks + Context). No Redux or Zustand.

### 9.1 Entry Point & Routing

**`main.jsx`**: Wraps the app in `<BrowserRouter>` and `<AuthProvider>`. Imports `styles.css` (Tailwind entry).

**`App.jsx`** route table:

| Path | Component | Guard |
|---|---|---|
| `/login` | `Login` | Public (redirects authenticated users to `/`) |
| `/` | `Dashboard` | `RequireAuth` → redirects to `/login` |
| `/upload` | `Upload` | `RequireAuth` → redirects to `/login` |

`RequireAuth` uses `useAuth()` to check token. Shows a loading spinner while the auth state is resolving.

**NavBar** (rendered in `App.jsx`): Links to Dashboard and Upload; shows logged-in email; Logout button calls `auth.logout()` and navigates to `/login`.

### 9.2 `auth.jsx` — Auth Context

```jsx
// Context shape
{
  user: { email, user_id } | null,
  token: string | null,
  loading: boolean,
  login(email, password): Promise<void>,
  register(email, password): Promise<void>,
  logout(): void
}
```

**Persistence**: JWT token stored in `localStorage` under key `expense_token`. On mount, if a token exists, calls `api.me()` to validate and hydrate `user`.

### 9.3 `api.js` — HTTP Client

Thin `fetch` wrapper. All calls attach `Authorization: Bearer <token>` from `localStorage`.

On 401/403 response: clears token from localStorage and reloads the page (forces re-login).

**Exported functions:**

| Function | Method | Path |
|---|---|---|
| `register(email, password)` | POST | `/api/auth/register` |
| `login(email, password)` | POST | `/api/auth/login` |
| `me()` | GET | `/api/auth/me` |
| `listExpenses()` | GET | `/api/expenses` |
| `summary()` | GET | `/api/summary` |
| `query(text)` | POST | `/api/query` |
| `getCategories()` | GET | `/api/categories` |
| `setCategories(list)` | PUT | `/api/categories` |
| `recategorize(id, category)` | PATCH | `/api/expenses/{id}` |
| `resetDb()` | POST | `/api/reset` |
| `upload(file)` | POST | `/api/upload` (FormData) |

### 9.4 Login Page

**File**: `pages/Login.jsx`

- Toggle button switches between **Login** and **Register** mode
- Fields: `email`, `password`
- On submit: calls `auth.login()` or `auth.register()`, then navigates to `/`
- Displays API error messages inline
- Redirects to `/` if `auth.user` is already set (prevents double-login)

### 9.5 Upload Page

**File**: `pages/Upload.jsx`

- Drag-and-drop zone and a "Browse" click-to-select fallback
- Accepted types: `.csv`, `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.tiff`, `.tif`, `.pdf`
- On file selection: calls `api.upload(file)`, shows loading spinner
- On success: renders a result table with columns `Date | Merchant | Category | Amount`
- On error: displays error message

### 9.6 Dashboard Page

**File**: `pages/Dashboard.jsx`

**Summary cards** (top row):
- Total Spent (sum of withdrawal amounts)
- Total Received (count label only — amounts obfuscated)
- Number of Expenses
- Number of Categories

**Bar chart** (Recharts `BarChart`):
- X axis: category names
- Y axis: total amount
- Data from `api.summary()`

**Natural-language search box**:
- Text input + Submit button
- Calls `api.query(text)` → renders result table below the chart
- Result table columns: `Date | Merchant | Category | Amount`

**Category editor**:
- Displays current categories as removable chips
- "Add category" text input
- Saves via `api.setCategories()`

**Recent expenses table**:
- Columns: `Date | Merchant | Category (dropdown) | Amount`
- Category column is an inline `<select>` populated with user categories
- On change: calls `api.recategorize(id, newCategory)`
- Learning indicator: shows a ★ badge next to merchants that have a saved category rule

**Deposits table**:
- Read-only table; amounts shown as obfuscated placeholders (e.g. `$11.11`)
- Privacy note below the table: *"Deposit values are obfuscated for privacy"*

**Reset DB button**: Calls `api.resetDb()` then reloads data. Intended for demo/testing.

---

## 10. Security Design

### 10.1 Authentication

- **Algorithm**: HS256 JWT
- **TTL**: 7 days
- **Secret validation**: `config.py` aborts startup if `JWT_SECRET` is absent or fewer than 16 characters
- **Enforcement**: every protected FastAPI route uses `Depends(current_user)` which decodes the bearer token and returns `user_id`

### 10.2 Multi-Tenancy Isolation

- Every Cloudant query includes `"user_id": user_id` in the Mango selector
- `store.get_expense()` verifies `doc["user_id"] == user_id` before returning
- Category rules are keyed by `user_id`
- COS objects are namespaced under `{user_id}/`

### 10.3 CORS

- Allow-list controlled by `ALLOWED_ORIGINS` environment variable
- `allow_credentials=False` — no cookie-based session; all auth is via bearer token in `Authorization` header

### 10.4 Password Security

- bcrypt with default cost factor (≥ 12 rounds)
- Passwords are never stored in plaintext
- `verify_credentials()` uses constant-time comparison via `bcrypt.checkpw()`

### 10.5 File Upload Security

- Size limit enforced before processing (HTTP 413 on violation)
- Extension validation in the router — unknown extensions are rejected before calling AI
- Files stored to COS with user-namespaced keys; no path traversal possible

### 10.6 Secrets Management

- Secrets are **never baked into the Docker image**
- Injected at runtime via environment variables or Code Engine secret references
- `Infra/secrets.env` is gitignored

---

## 11. AI Model Usage

### 11.1 Llama 3.2 Vision — Receipt OCR

**Model ID**: `meta-llama/llama-3-2-11b-vision-instruct`  
**Used for**: Image receipts and scanned (image-layer) PDFs

**Input**: base64-encoded image bytes  
**Output**: JSON array of expense rows

**System prompt contract** (must be preserved):
- Extract one row per line item or one row for the overall receipt total
- Fields: `date`, `merchant`, `amount` (numeric), `currency` (ISO code), `category`, `flow` (`"withdrawal"` or `"deposit"`)
- Return only valid JSON, no prose
- If a field is unknown, use `null`

### 11.2 Granite 3 — Text Normalization & NL Query

**Model ID**: `ibm/granite-3-8b-instruct`  
**Used for**: CSV normalization, text-PDF normalization, and NL query parsing

**CSV/PDF system prompt contract**:
- Input is raw text from a bank statement, CSV, or PDF
- Output: JSON array of rows with `date`, `merchant`, `amount`, `currency`, `category`, `flow`
- The `flow` field must be `"withdrawal"` or `"deposit"` — never omit it
- Do not invent amounts; if a value is illegible, emit `null`

**NL Query system prompt contract**:
- Input is a natural-language expense query
- Output: `{"categories": [...], "date_from": "YYYY-MM-DD", "date_to": "YYYY-MM-DD"}`
- Omit keys that cannot be inferred
- Categories must exactly match the user's category list

### 11.3 Prompt Contracts

The AI prompts are the system's most critical interface. Changing them requires re-testing all parser paths. Key invariants:
- Models always respond with JSON only (no markdown fences in the returned value)
- `_extract_json()` provides defensive fallback for truncated output
- `temperature=0.0` ensures deterministic results across identical inputs

---

## 12. Category Learning Loop

The learning loop allows manual corrections to automatically apply to future and past expenses from the same merchant.

**Trigger**: User changes a category in the Dashboard expense table.

**Flow**:
1. Frontend: `api.recategorize(expense_id, new_category)` → `PATCH /api/expenses/{id}`
2. Backend: update the expense document in Cloudant
3. Backend: `store.upsert_category_rule(user_id, normalize_merchant(merchant), new_category)` — creates or updates a `category_rule` doc
4. Backend (back-apply): query all expenses for this user → for every expense whose normalized merchant key matches → update category and upsert

**Forward application** (during ingest):
- `pipeline.process_file()` loads all category rules at the start
- After building each expense, checks `normalize_merchant(expense["merchant"])` against the rules map
- If a match is found, overrides the AI-assigned category with the learned one

**Key constraint**: `schema.normalize_merchant()` must produce the same output in all three locations: rule creation, back-apply, and ingest forward-apply. Never replace it with a different normalization.

---

## 13. Deposit Privacy

Deposit amounts are obfuscated before storage so that a dashboard screenshot does not reveal income.

**Detection** (`parsers._is_deposit()`):
- Explicit `flow: "deposit"` field from AI output
- OR text contains `"dépôt"`, `"depot"`, `"deposit"` (case-insensitive)
- OR transaction code starts with `"DI"` (common in Canadian bank statements)

**Obfuscation** (`parsers._obfuscate_amount()`):
- Replace every integer digit in the amount with `1`
- Examples: `1234.56 → 1111.11`, `45.00 → 11.00`, `500 → 111`
- The decimal structure (number of decimal places) is preserved

**Storage**: Deposits are stored as standard expense documents with `flow: "deposit"`. No separate collection or schema.

**Frontend**: The Deposits table displays the obfuscated amounts. A privacy note is shown below the table. Deposit amounts are excluded from all "Total Spent" calculations.

---

## 14. API Reference

All routes under `/api/` require `Authorization: Bearer <token>` except the auth routes.

### 14.1 Auth Endpoints

#### `POST /api/auth/register`
```json
Request:  { "email": "user@example.com", "password": "secret" }
Response: { "access_token": "<jwt>", "token_type": "bearer", "email": "user@example.com" }
Errors:   409 Conflict — email already registered
```

#### `POST /api/auth/login`
```json
Request:  { "email": "user@example.com", "password": "secret" }
Response: { "access_token": "<jwt>", "token_type": "bearer", "email": "user@example.com" }
Errors:   401 Unauthorized — wrong credentials
```

#### `GET /api/auth/me`
```json
Response: { "email": "user@example.com", "user_id": "<uuid>" }
```

### 14.2 Upload Endpoint

#### `POST /api/upload`
```
Content-Type: multipart/form-data
Body: file=<binary>

Response 200:
{
  "count": 3,
  "expenses": [
    { "_id": "...", "date": "2024-01-10", "merchant": "...", "amount": 12.5, "category": "Dining", ... }
  ]
}

Errors:
  413 — file exceeds MAX_UPLOAD_MB
  400 — unsupported file type
```

### 14.3 Expense Endpoints

#### `GET /api/expenses`
```json
Response: {
  "expenses": [ <expense docs with flow="withdrawal"> ],
  "deposits": [ <expense docs with flow="deposit"> ]
}
```

#### `GET /api/summary`
```json
Response: {
  "count": 42,
  "total": 1234.56,
  "by_category": { "Dining": 300.0, "Groceries": 450.0, ... }
}
```

#### `GET /api/categories`
```json
Response: { "categories": ["Groceries", "Dining", ...] }
```

#### `PUT /api/categories`
```json
Request:  { "categories": ["Groceries", "Dining", "Custom"] }
Response: { "categories": ["Groceries", "Dining", "Custom"] }
```

#### `PATCH /api/expenses/{id}`
```json
Request:  { "category": "Dining" }
Response: { <updated expense doc> }
```
Side effects: saves category rule, back-applies to matching merchant.

#### `POST /api/query`
```json
Request:  { "query": "show me dining expenses last month" }
Response: {
  "expenses": [ <filtered expense docs> ],
  "filter": { "categories": ["Dining"], "date_from": "2024-01-01", "date_to": "2024-01-31" }
}
```

#### `GET /api/chart.png`
Returns `image/png` binary. Pie chart of expenses by category for the logged-in user.

#### `POST /api/reset`
```json
Response: { "deleted": 42 }
```
Deletes all expense documents for the current user. Irreversible. For demo use only.

---

## 15. Configuration Reference

All configuration is loaded by `agent/config.py`. The `Infra/secrets.env` file is loaded automatically when running locally.

**Full example `Infra/secrets.env`**:
```env
# watsonx.ai
WATSONX_APIKEY=<ibm-cloud-apikey>
WATSONX_PROJECT_ID=<project-uuid>
WATSONX_URL=https://us-south.ml.cloud.ibm.com

# Cloud Object Storage
COS_APIKEY=<ibm-cloud-apikey>
COS_ENDPOINT=https://s3.us-south.cloud-object-storage.appdomain.cloud
COS_HMAC_ACCESS_KEY=<hmac-access>
COS_HMAC_SECRET_KEY=<hmac-secret>
COS_BUCKET=expense-tracker-uploads

# Cloudant
CLOUDANT_URL=https://<instance>.cloudantnosqldb.appdomain.cloud
CLOUDANT_APIKEY=<ibm-cloud-apikey>
CLOUDANT_DB=expenses

# Web / Auth
JWT_SECRET=<at-least-16-chars-random-string>
ALLOWED_ORIGINS=http://localhost:5173,https://your-app.us-south.codeengine.appdomain.cloud
MAX_UPLOAD_MB=20

# Gmail poller (optional — only needed for main.py)
GMAIL_CLIENT_ID=<oauth-client-id>
GMAIL_CLIENT_SECRET=<oauth-client-secret>
GMAIL_REFRESH_TOKEN=<oauth-refresh-token>
GMAIL_USER_ID=you@gmail.com
```

---

## 16. Deployment

### 16.1 Docker Build

Multi-stage `web/Dockerfile`:

**Stage 1 — Frontend build** (node:20-alpine):
```dockerfile
WORKDIR /app/frontend
COPY web/frontend/package*.json .
RUN npm ci
COPY web/frontend .
RUN npm run build          # outputs to dist/
```

**Stage 2 — Python runtime** (python:3.12-slim):
```dockerfile
# System libraries for image/PDF processing
RUN apt-get install -y libjpeg-dev zlib1g-dev libfreetype6-dev

# Python dependencies (web backend + agent core)
COPY web/backend/requirements.txt .
COPY agent/requirements.txt agent-requirements.txt
RUN pip install -r requirements.txt -r agent-requirements.txt

# App source
COPY agent/ agent/
COPY web/backend/ .

# Built frontend
COPY --from=0 /app/frontend/dist web/frontend/dist

EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
```

### 16.2 IBM Code Engine

**Create and deploy:**
```bash
# Build and push from source
ibmcloud ce app create \
  --name expense-tracker \
  --build-source . \
  --build-dockerfile web/Dockerfile \
  --port 8080 \
  --min-scale 0 \
  --max-scale 5

# Inject secrets
ibmcloud ce app update \
  --name expense-tracker \
  --env-from-secret expense-secrets

# Create the secret (one-time)
ibmcloud ce secret create \
  --name expense-secrets \
  --from-env-file Infra/secrets.env
```

**Key settings:**
- Port: 8080
- `min-scale: 0` → scales to zero when idle (cost savings)
- `max-scale: 5` → handles concurrent uploads
- Secrets are mounted as environment variables at runtime

### 16.3 Local Development

**Backend:**
```bash
cd web/backend
pip install -r requirements.txt
# Ensure agent/ requirements are also installed
pip install -r ../../agent/requirements.txt
# Run with secrets loaded from file
uvicorn app:app --reload --port 8000
```

**Frontend:**
```bash
cd web/frontend
npm install
npm run dev   # starts on :5173, proxies /api to :8000
```

**Production parity test** (without Docker):
```bash
cd web/frontend && npm run build
cd ../backend && uvicorn app:app --port 8000
# Backend now serves built SPA at localhost:8000
```

**Gmail poller (standalone):**
```bash
cd agent
python main.py          # one-shot
python main.py --loop   # continuous (60s interval)
```

---

## 17. Testing

### 17.1 Agent Smoke Test

**File**: `agent/test_smoke.py`

Tests the full pipeline without live IBM services by mocking external calls.

**Critical import order** (must be preserved):
```python
# Set fake env vars BEFORE importing config
os.environ["WATSONX_APIKEY"] = "fake"
os.environ["JWT_SECRET"] = "fake-secret-16chars"
# ... all other vars ...

# Only then import shared modules
import config
import schema
import pipeline
```

Run:
```bash
python -m pytest agent/test_smoke.py -q
```

### 17.2 Web Backend Smoke Test

**File**: `web/backend/test_web_smoke.py`

Tests the FastAPI routes using `TestClient`. Also pre-seeds env vars before importing `app`.

Run from the **repo root** (required for `sys.path` injection to resolve `agent/`):
```bash
python -m pytest web/backend/test_web_smoke.py -q
```

### 17.3 Test Coverage Areas

| Area | Covered |
|---|---|
| User register/login/JWT | ✅ |
| File upload → pipeline | ✅ |
| Expense list + summary | ✅ |
| NL query parsing | ✅ |
| Category CRUD | ✅ |
| Recategorize + back-apply | ✅ |
| Idempotent re-upload | ✅ |
| Deposit obfuscation | ✅ |
| Data isolation (cross-user) | ✅ |

---

## 18. Non-Functional Requirements

| Requirement | Design Decision |
|---|---|
| **Idempotency** | SHA-256 doc IDs; uploading same file twice is a no-op |
| **Multi-tenancy** | Every DB query and object key includes `user_id` |
| **Scalability** | Stateless FastAPI; Code Engine autoscale; Cloudant scales independently |
| **Cold start** | `min-scale: 0` accepted trade-off; lazy AI library imports reduce startup time |
| **Privacy** | Deposit obfuscation; secrets never in image; bearer tokens (not cookies) |
| **Resilience** | `_extract_json()` repairs truncated LLM output; store read failures return `[]` |
| **Observability** | All errors logged to stdout (captured by Code Engine logs) |
| **Cost** | All IBM services with pay-as-you-go; scales to zero |

---

## 19. Known Constraints & Design Decisions

### No ORM or Data Layer Abstraction
Cloudant is accessed via raw REST calls. This was a deliberate choice to minimize dependencies and maintain full control over request construction, IAM token caching, and error handling.

### No Message Queue
The two ingest paths (web upload and Gmail poller) invoke `pipeline.process_file()` synchronously. For high-volume production use, this should be replaced with a job queue (e.g., IBM MQ or a Cloudant-backed queue).

### Single Cloudant Database
All document types (`expense`, `user`, `category_rule`, `settings`) share one database and are differentiated by the `type` field. Separate databases per tenant or per type would improve query performance at scale but add operational complexity.

### bcrypt 72-Byte Limit
bcrypt truncates input at 72 bytes. Passwords longer than 72 bytes are silently accepted but only the first 72 bytes are hashed. This is a known bcrypt limitation and is acceptable for this use case.

### First-Page-Only PDF Rasterization
When a scanned PDF is detected, only the first page is rasterized and sent to the Vision model. Multi-page scanned PDFs will only extract the first page's expenses. This is a deliberate simplification.

### No Refresh Token
JWTs have a 7-day TTL with no refresh mechanism. Users must re-login after expiry.

### sys.path Injection Instead of Packages
`agent/` is not a proper Python package (no `__init__.py`). The backend injects it into `sys.path` at startup. This is intentional to keep the agent usable as standalone scripts without installation.

### Frontend Builds Produce No Unit Tests
Frontend testing (React Testing Library, Vitest) is not configured. The smoke tests cover the full API contract, which provides sufficient confidence for the submission scope.
