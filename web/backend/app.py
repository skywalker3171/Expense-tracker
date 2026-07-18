"""app.py — FastAPI entrypoint. Serves API + built frontend (single service)."""
from __future__ import annotations
import os, sys

_AGENT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "agent"))
if _AGENT_DIR not in sys.path:
    sys.path.insert(0, _AGENT_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(_AGENT_DIR, "..", "Infra", "secrets.env"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import config
import auth
import routes_upload
import routes_expenses

app = FastAPI(title="Expense Tracker API", version="1.0")

_origins = ["*"] if config.ALLOWED_ORIGINS == "*" else [o.strip() for o in config.ALLOWED_ORIGINS.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,            prefix="/api/auth", tags=["auth"])
app.include_router(routes_upload.router,   prefix="/api",      tags=["upload"])
app.include_router(routes_expenses.router, prefix="/api",      tags=["expenses"])


@app.get("/api/health")
def health():
    return {"status": "ok"}


# --- Static frontend (production) ---------------------------------------------
# The built Vite bundle is copied into the image. When present, serve it so the
# API and SPA share one origin. Absent in local dev (use `vite` dev server).
_DEFAULT_DIST = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
)
FRONTEND_DIST_DIR = os.environ.get("FRONTEND_DIST_DIR", _DEFAULT_DIST)

if os.path.isdir(FRONTEND_DIST_DIR):
    _assets = os.path.join(FRONTEND_DIST_DIR, "assets")
    if os.path.isdir(_assets):
        app.mount("/assets", StaticFiles(directory=_assets), name="assets")

    _index = os.path.join(FRONTEND_DIST_DIR, "index.html")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        # Serve real files if they exist (favicon, etc.), else the SPA shell.
        candidate = os.path.join(FRONTEND_DIST_DIR, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(_index)
