"""Local no-Docker smoke test for the production serving path.

Exercises the exact same FastAPI app the container runs (API + built SPA on
one origin) using Starlette's in-process TestClient. No Docker, no open port.

Run (from repo root, .venv active):
    .\\.venv\\Scripts\\python.exe -m pytest web/backend/test_web_smoke.py -q
or simply:
    .\\.venv\\Scripts\\python.exe web/backend/test_web_smoke.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from fastapi.testclient import TestClient

import app as web_app

client = TestClient(web_app.app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_auth_routes_registered():
    paths = {getattr(rt, "path", "") for rt in web_app.app.routes}
    for expected in ("/api/auth/register", "/api/auth/login", "/api/upload",
                     "/api/expenses", "/api/summary", "/api/chart.png"):
        assert expected in paths, f"missing route {expected}"


def test_protected_route_requires_auth():
    # No bearer token -> 401/403, never a 200.
    r = client.get("/api/expenses")
    assert r.status_code in (401, 403)


def test_spa_served_when_built():
    # Only meaningful once `npm run build` has produced web/frontend/dist.
    if not os.path.isdir(web_app.FRONTEND_DIST_DIR):
        print("SKIP spa test: no dist/ (run `npm run build` in web/frontend)")
        return
    root = client.get("/")
    assert root.status_code == 200
    assert "text/html" in root.headers.get("content-type", "")
    # Unknown client-side route falls back to the SPA shell (index.html).
    spa = client.get("/dashboard")
    assert spa.status_code == 200
    assert "text/html" in spa.headers.get("content-type", "")


if __name__ == "__main__":
    test_health()
    test_auth_routes_registered()
    test_protected_route_requires_auth()
    test_spa_served_when_built()
    print("ALL WEB SMOKE CHECKS PASSED")
