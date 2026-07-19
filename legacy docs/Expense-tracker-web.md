# Expense Tracker — Web App & Multi-Tenant Migration Plan

> **Goal:** Turn the current single-tenant, shared-inbox agent into a real multi-user
> product. Each user logs into a web app and uploads their own receipts; the existing
> watsonx.ai pipeline (OCR to categorize to chart) is reused unchanged. Nobody emails a
> stranger's inbox anymore.
>
> This document is the implementation plan for **Option 1 - flip the ingest interface
> to a user-facing upload and partition all data per user.**

---

## 0. Guiding principles

- **Reuse the AI core.** `router.py`, `parsers.py`, `watsonx_client.py`, and `chart.py`
  are the valuable part and change as little as possible.
- **Add a `user_id` dimension end-to-end.** Every expense doc, every COS object key,
  and every query is scoped to a user.
- **Add a second ingest path, don't rip out the first.** The Gmail poller keeps working;
  the new HTTP upload path becomes the primary interface.
- **Stay on IBM Cloud.** Cloudant, COS, and watsonx.ai remain the backend, keeping the
  all-IBM architecture story intact for the watsonx challenge.

---

## 1. Target architecture

Two ingest paths feed one shared processing core:

1. **Web upload (new, primary):** Browser -> Web API (`/api/upload`) -> `process_upload()`
   -> router -> watsonx.ai -> store (COS + Cloudant), all scoped to the logged-in `user_id`.
2. **Gmail poller (existing, secondary):** Code Engine cron -> `run_once()` -> same router
   -> watsonx.ai -> store. Retained for the "forward to your connected mailbox" feature.

Shared core (unchanged):
`router.route()` -> `parsers` / `watsonx_client` -> `schema.build_expense()` -> `store`.

Backend services (unchanged): IBM COS (raw files), IBM Cloudant (expense docs),
watsonx.ai (Llama vision OCR + Granite categorize).

New pieces: a web API service, user authentication, and a browser dashboard.

---

## 2. Data model changes

Add a `user_id` to the canonical expense document and make the doc id unique per user.

New expense doc shape (added/changed fields in **bold** conceptually):

- `id`: `sha256(user_id + ":" + source_ref + ":" + line_index)`  (was email_id + line_index)
- `user_id`: string (owner of the expense) — NEW
- `source_ref`: gmail message id OR upload id — RENAMED from `source_email_id`
- `source_type`: `pdf | image | csv` (unchanged)
- all other fields (`date`, `merchant`, `amount`, `currency`, `category`, `raw_text`,
  `created_at`) unchanged.

Cloudant index: create a Mango index on `user_id` (and `date`) so per-user queries are fast.

COS key layout: `{user_id}/{source_ref}/{filename}` so raw files are namespaced per user.

---

## A. Agent code changes

Ordered, file-by-file. Keep changes backward compatible so the Gmail path still works.

### A1. `schema.py`
- Add `user_id` to `EXPENSE_KEYS`.
- Change `make_id(user_id, source_ref, line_index)` to hash all three, so ids are unique
  across users even for the same source file.
- Update `build_expense(...)` signature: add required `user_id`; rename `source_email_id`
  param to `source_ref` (keep a `source_email_id` alias for the Gmail caller if desired).
- Add `user_id` presence check to `validate_expense()`.

### A2. `store.py`
- `upsert_expense(doc)`: no signature change; docs now carry `user_id`.
- `query_expenses(user_id, selector=None)`: add a required `user_id` and inject
  `{"user_id": user_id}` into the Mango selector so a user only ever sees their own rows.
- Add `ensure_user_index()` that creates a Cloudant Mango index on `["user_id", "date"]`.
- `upload_attachment(user_id, source_ref, filename, data)`: prefix the COS key with
  `{user_id}/` so raw files are namespaced.

### A3. `pipeline.py` (NEW — extracted shared core)
- Extract "process one file" logic out of `main.py` so both ingest paths call the same code:
  - `process_file(*, user_id, source_ref, filename, mime_type, data) -> list[dict]`
    1. `store.upload_attachment(user_id, source_ref, filename, data)`
    2. `expenses = router.route(data, filename, mime_type, source_ref)` (route stays generic)
    3. attach `user_id` to each expense via `build_expense`
    4. `store.upsert_expense(doc)` for each
    5. return the stored expenses
- `main.py` `_handle_attachment()` becomes a thin wrapper that calls `process_file()` with
  `user_id = <owner of connected mailbox>` and `source_ref = msg_id`.

### A4. `router.py`
- Rename the `source_email_id` param to `source_ref` throughout (pure rename; behavior
  identical). No routing logic changes.

### A5. `main.py`
- Keep `run_once()` / `--loop` for the Gmail cron path.
- Route each processed message through `pipeline.process_file()` instead of inline logic.
- Chart requests call `store.query_expenses(user_id=<mailbox owner>)`.

### A6. `config.py`
- Add web/auth config: `JWT_SECRET`, `SESSION_SECRET`, OIDC/App ID client id+secret (if
  used), `MAX_UPLOAD_MB`, and `ALLOWED_ORIGINS` for CORS.

### A7. `chart.py`
- No signature change needed; it already takes a list of expense dicts. The web API will
  pass in the per-user list from `query_expenses(user_id=...)`.

---

## B. Web app skeleton

Recommended stack: **FastAPI** backend (reuses the existing Python agent modules directly)
plus a lightweight **React + Vite** frontend. FastAPI is the pragmatic choice because the
whole pipeline is already Python, so the web layer imports `pipeline`, `store`, and `chart`
with zero rewrites.

### B1. Proposed repo layout

```
web/
  backend/
    app.py            # FastAPI app + route registration + CORS
    auth.py           # login, JWT issue/verify, get_current_user dependency
    routes_upload.py  # POST /api/upload  -> pipeline.process_file
    routes_expenses.py# GET /api/expenses, GET /api/summary, GET /api/chart.png
    deps.py           # shared FastAPI dependencies (current_user, settings)
    requirements.txt  # fastapi, uvicorn, python-multipart, PyJWT, passlib[bcrypt]
  frontend/
    index.html
    package.json      # react, react-dom, vite, recharts (or chart.js)
    src/
      main.jsx        # React entry
      api.js          # fetch wrapper that attaches the JWT bearer token
      App.jsx         # router + auth guard
      pages/
        Login.jsx     # email/password (or "Sign in with IBM App ID")
        Dashboard.jsx # summary cards + pie chart + recent expenses
        Upload.jsx    # drag-and-drop receipt upload + progress
      components/
        ExpenseTable.jsx
        CategoryPie.jsx
  Dockerfile          # multi-stage: build frontend, serve via FastAPI static mount
  README.md
```

The backend imports the existing agent modules (add `agent/` to `PYTHONPATH`, or make the
agent an installable package). No agent logic is duplicated.

### B2. API surface

- `POST /api/auth/register` — create user (email + password) -> returns JWT.
- `POST /api/auth/login` — verify credentials -> returns JWT.
- `GET  /api/me` — current user profile.
- `POST /api/upload` — multipart file upload; runs `pipeline.process_file(user_id=me, ...)`;
  returns the extracted expenses.
- `GET  /api/expenses` — list current user's expenses (`query_expenses(user_id=me)`).
- `GET  /api/summary` — category totals for the dashboard cards.
- `GET  /api/chart.png` — pie chart PNG from `chart.build_pie_chart(...)`.

### B3. Auth model

- Minimal viable: email + password, hashed with `passlib[bcrypt]`, stored as a user doc in
  Cloudant (`type: "user"`). Issue a signed JWT; frontend stores it and sends it as
  `Authorization: Bearer <token>`.
- `get_current_user` FastAPI dependency decodes the JWT and yields `user_id`; every data
  route depends on it so a request can only ever touch its own `user_id`.
- Upgrade path (recommended for the challenge): swap local auth for **IBM App ID** (OIDC).
  This keeps the all-IBM story and offloads password/security concerns.

### B4. Backend skeleton (`app.py`)

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import routes_upload, routes_expenses, auth

app = FastAPI(title="Expense Tracker API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(auth.router,             prefix="/api/auth", tags=["auth"])
app.include_router(routes_upload.router,    prefix="/api",      tags=["upload"])
app.include_router(routes_expenses.router,  prefix="/api",      tags=["expenses"])
```

### B5. Upload route skeleton (`routes_upload.py`)

```python
import uuid
from fastapi import APIRouter, UploadFile, File, Depends
import pipeline
from deps import current_user

router = APIRouter()

@router.post("/upload")
async def upload(file: UploadFile = File(...), user=Depends(current_user)):
    data = await file.read()
    source_ref = f"upload-{uuid.uuid4().hex}"
    expenses = pipeline.process_file(
        user_id=user["id"],
        source_ref=source_ref,
        filename=file.filename,
        mime_type=file.content_type or "application/octet-stream",
        data=data,
    )
    return {"count": len(expenses), "expenses": expenses}
```

### B6. Expenses/chart route skeleton (`routes_expenses.py`)

```python
from fastapi import APIRouter, Depends
from fastapi.responses import Response
import store, chart
from deps import current_user

router = APIRouter()

@router.get("/expenses")
def list_expenses(user=Depends(current_user)):
    return store.query_expenses(user_id=user["id"])

@router.get("/chart.png")
def chart_png(user=Depends(current_user)):
    expenses = store.query_expenses(user_id=user["id"])
    png = chart.build_pie_chart(expenses)
    return Response(content=png, media_type="image/png")
```

### B7. Frontend flow

1. **Login/Register** -> store JWT in memory (or `localStorage` for the demo).
2. **Upload page** -> drag-and-drop a receipt -> `POST /api/upload` -> show extracted rows.
3. **Dashboard** -> `GET /api/summary` for cards, `GET /api/chart.png` for the pie,
   `GET /api/expenses` for the table.

---

## C. Phased task list

- **Phase W0 — Multi-tenant data layer** (DONE)
  - [x] W0.1 `schema.py`: add `user_id`, update `make_id` / `build_expense` / `validate_expense`.
  - [x] W0.2 `store.py`: scope `query_expenses` by `user_id`; namespace COS keys; add index.
  - [x] W0.3 `pipeline.py`: extract `process_file()`; wire `main.py` to it.
  - [x] W0.4 `router.py`: rename `source_email_id` -> `source_ref`.

- **Phase W1 — Backend API** (DONE)
  - [x] W1.1 Scaffold FastAPI app + CORS.
  - [x] W1.2 Auth: register/login, JWT, `get_current_user`.
  - [x] W1.3 `/api/upload` calling `pipeline.process_file`.
  - [x] W1.4 `/api/expenses`, `/api/summary`, `/api/chart.png`.

- **Phase W2 — Frontend** (DONE)
  - [x] W2.1 Vite + React scaffold, auth guard, token storage.
  - [x] W2.2 Upload page (drag-and-drop) + result view.
  - [x] W2.3 Dashboard (cards + pie + expense table).

- **Phase W3 — Deploy & test** (DONE)
  - [x] W3.1 Dockerfile (multi-stage: build frontend, serve via FastAPI static mount).
  - [x] W3.2 Deploy to IBM Code Engine as an app; inject secrets via `--env-from-secret`.
        (Documented in `web/README.md` using `--build-source` so no local Docker is needed.)
  - [x] W3.3 Keep the Gmail cron path deployed alongside (optional).

---

## D. Deployment notes

- Package the `agent/` modules so the web backend can import them (simplest: copy `agent/`
  into the image and set `PYTHONPATH=/app/agent`, or `pip install -e .`).
- One container serves both the API and the built static frontend (FastAPI `StaticFiles`
  mount), so a single Code Engine app is enough.
- Reuse the existing `expense-secrets` secret; add `JWT_SECRET` to it.

---

## E. Acceptance criteria

- [ ] A new user can register and log in; a JWT is issued.
- [ ] An authenticated user uploads a receipt (CSV / image / PDF) and sees extracted,
      categorized expenses returned.
- [ ] Uploaded expenses are stored in Cloudant tagged with the correct `user_id`, and the
      raw file lands in COS under `{user_id}/...`.
- [ ] `GET /api/expenses` returns **only** the calling user's rows (verified by creating a
      second user and confirming isolation).
- [ ] The dashboard renders per-user summary cards, pie chart, and expense table.
- [ ] Re-uploading the same file does not create duplicate expense docs (idempotency via
      the deterministic `id`).
- [ ] The existing Gmail cron path still works unchanged after the refactor.


