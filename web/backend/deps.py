"""
deps.py — JWT helpers and the FastAPI current_user dependency.
"""
from __future__ import annotations

import time
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import config

_ALGO = "HS256"
_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days

# auto_error=False so a *missing* Authorization header surfaces as our own
# 401 (semantically correct for authentication) rather than FastAPI's default
# 403. The SPA's recovery flow (clear token, redirect to login) keys off 401.
_bearer = HTTPBearer(auto_error=False)


def issue_token(*, user_id: str, email: str) -> str:
    """Create a signed JWT for a user."""
    now = int(time.time())
    payload = {
        "sub": user_id,
        "email": email,
        "iat": now,
        "exp": now + _TTL_SECONDS,
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=_ALGO)


def current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    """Decode the bearer token and return {"id": ..., "email": ...}.

    Every data route depends on this, so a request can only ever touch its own
    user_id. A missing or malformed credential returns 401 (not 403) so the SPA
    can uniformly detect an unauthenticated state and redirect to login.
    """
    if creds is None or not creds.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated")

    token = creds.credentials
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[_ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")
    return {"id": payload["sub"], "email": payload.get("email", "")}
