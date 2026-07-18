# Expense Tracker — Web App

Multi-user web frontend + FastAPI backend that reuses the existing `agent/`
watsonx.ai pipeline (OCR → categorize → chart). One container serves both the
API and the built React SPA.

## Local development

Run the backend and the Vite dev server separately (Vite proxies `/api` → :8000).

```
# terminal 1 — backend (from repo root, .venv active)
uvicorn app:app --reload --port 8000 --app-dir web/backend

# terminal 2 — frontend
cd web/frontend
npm install
npm run dev        # http://localhost:5173
```

Secrets are read from `Infra/secrets.env` in local dev (loaded by `app.py`).
`JWT_SECRET` defaults to an insecure dev value if unset.

## Testing locally WITHOUT Docker

Docker is **not** required to test the app locally. The container image only
bundles the same Python backend + built frontend you can run directly, so you
have three equivalent no-Docker options:

**1. Production-parity, single origin (matches the container exactly).**
Build the frontend once, then let FastAPI serve it on one port — identical to
how the Code Engine container behaves:

```
cd web/frontend && npm install && npm run build && cd ../..
uvicorn app:app --port 8000 --app-dir web/backend      # http://localhost:8000
```

`app.py` auto-detects `web/frontend/dist` and mounts it, so the SPA and API are
served same-origin at `http://localhost:8000` — no Docker, no separate port.

**2. Fast dev loop (hot reload).** Run the two dev servers as shown under
"Local development" above (`uvicorn --reload` + `npm run dev`). Vite proxies
`/api` to the backend, so you get instant frontend reloads.

**3. Automated smoke test (no servers, no port).** Exercises the exact
production app in-process via Starlette's `TestClient`:

```
.\.venv\Scripts\python.exe web\backend\test_web_smoke.py
```

Checks the health route, that all API routes are registered, that protected
routes reject unauthenticated requests, and — if `web/frontend/dist` exists —
that the SPA is served with client-side-route fallback. This is the closest
you can get to "did my container work?" without ever building an image.

## Deploy to IBM Code Engine (no local Docker required)

Code Engine builds the image remotely from source, so you don't need Docker
installed locally. Run these from the **repo root** (`c:\Dev\WatsonX`).

```
# 1. Log in and target your project
ibmcloud login --sso
ibmcloud target -g <resource-group> -r <region>       # e.g. us-south
ibmcloud ce project select --name <your-ce-project>   # or: project create --name expense-tracker

# 2. Reuse the existing secret and add JWT_SECRET to it
ibmcloud ce secret update --name expense-secrets \
    --from-literal JWT_SECRET="$(python -c "import secrets;print(secrets.token_urlsafe(48))")"

# 3. Build + deploy the app straight from source (remote Kaniko build)
ibmcloud ce app create \
    --name expense-tracker-web \
    --build-source . \
    --build-dockerfile web/Dockerfile \
    --port 8080 \
    --env-from-secret expense-secrets \
    --env ALLOWED_ORIGINS="*" \
    --cpu 1 --memory 2G \
    --min-scale 0

# 4. Get the public URL
ibmcloud ce app get --name expense-tracker-web --output url
```

To ship code changes later, rebuild in place:

```
ibmcloud ce app update --name expense-tracker-web \
    --build-source . --build-dockerfile web/Dockerfile
```

Notes:
- `--build-source .` uploads the repo and builds remotely; the `.dockerignore`
  at the repo root keeps `secrets.env`, `node_modules`, and `.venv` out of the
  build context.
- `expense-secrets` must already contain the Cloudant / COS / watsonx.ai /
  Gmail vars used by `agent/config.py`. Step 2 just adds `JWT_SECRET`.
- The app listens on `$PORT` (8080). Code Engine sets `PORT` automatically.

## W3.3 — Gmail cron path (optional, unchanged)

The original Gmail poller still runs independently. Deploy it as a Code Engine
job/cron using the existing `agent/` code, invoking `python main.py --loop`.
It shares the same `expense-secrets` and writes to the same Cloudant DB,
attributing its expenses to `GMAIL_USER_ID`.
