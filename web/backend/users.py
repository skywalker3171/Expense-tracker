"""
users.py — user records stored in Cloudant (type: "user").

Reuses the agent's Cloudant REST auth pattern via store._headers()/_BASE.
Passwords are hashed with bcrypt (direct, no passlib). A user doc looks like:
    {"_id": "user:<email>", "type": "user", "email": ..., "password_hash": ...,
     "user_id": "<uuid>", "created_at": ...}
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import requests
import bcrypt

import config
import store

log = logging.getLogger(__name__)

# bcrypt only hashes the first 72 bytes of a password; longer inputs raise in
# newer bcrypt releases. Truncate defensively so any password is accepted.
def _pw_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:72]


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(_pw_bytes(password), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(_pw_bytes(password), password_hash.encode("utf-8"))
    except ValueError:
        return False


def _doc_id(email: str) -> str:
    return "user:" + email.strip().lower()


def get_user(email: str) -> dict | None:
    """Return the user doc for an email, or None if not found."""
    store._ensure_db()
    url = store._BASE + "/" + config.CLOUDANT_DB + "/" + _doc_id(email)
    r = requests.get(url, headers=store._headers(), timeout=30)
    if r.status_code == 200:
        return r.json()
    return None


def create_user(email: str, password: str) -> dict:
    """Create a new user. Raises ValueError if the email already exists."""
    email = email.strip().lower()
    if get_user(email) is not None:
        raise ValueError("email already registered")
    doc = {
        "_id":           _doc_id(email),
        "type":          "user",
        "email":         email,
        "password_hash": _hash_password(password),
        "user_id":       uuid.uuid4().hex,
        "created_at":    datetime.now(timezone.utc).isoformat(),
    }
    url = store._BASE + "/" + config.CLOUDANT_DB + "/" + doc["_id"]
    r = requests.put(url, headers=store._headers(), json=doc, timeout=30)
    if r.status_code not in (201, 202):
        log.error("create_user failed %s %s", r.status_code, r.text)
        r.raise_for_status()
    return doc


def verify_credentials(email: str, password: str) -> dict | None:
    """Return the user doc if email+password match, else None."""
    user = get_user(email)
    if user is None:
        return None
    if not _verify_password(password, user.get("password_hash", "")):
        return None
    return user
