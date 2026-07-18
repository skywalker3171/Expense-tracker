"""
auth.py — registration, login, and profile routes.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

import users
from deps import current_user, issue_token

router = APIRouter()


class Credentials(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    email: str


@router.post("/register", response_model=TokenResponse)
def register(body: Credentials):
    try:
        user = users.create_user(str(body.email), body.password)
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    token = issue_token(user_id=user["user_id"], email=user["email"])
    return TokenResponse(access_token=token, email=user["email"])


@router.post("/login", response_model=TokenResponse)
def login(body: Credentials):
    user = users.verify_credentials(str(body.email), body.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    token = issue_token(user_id=user["user_id"], email=user["email"])
    return TokenResponse(access_token=token, email=user["email"])


@router.get("/me")
def me(user=Depends(current_user)):
    return {"user_id": user["id"], "email": user["email"]}
