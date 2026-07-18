"""
deps.py — JWT helpers and the FastAPI current_user dependency.
"""
from __future__ import annotations

import time

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import config

_ALGO = "HS256"
_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days

_bearer = HTTPBearer(auto_error=True)


def issue_token(*, user_id: str, email: str) -> str:
    """Create a signed JWT for a user."""
    now = int(time.time())
    payload = {
        "sub":   user_id,
        "email": email,
        "iat":   now,
        "exp":   now + _TTL_SECONDS,
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=_ALGO)


def current_user(creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict:
    """Decode the bearer token and return {"id": ..., "email": ...}.

    Every data route depends on this, so a request can only ever touch its own
    user_id.
    """
    token = creds.credentials
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[_ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")
    return {"id": payload["sub"], "email": payload.get("email", "")}
