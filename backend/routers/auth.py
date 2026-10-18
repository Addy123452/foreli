"""Authentication endpoints (register / login / logout / me)."""
import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from .. import schemas
from ..auth import (
    COOKIE_NAME,
    SESSION_DAYS,
    create_session,
    get_current_user,
    hash_password,
    verify_password,
)
from ..db import get_db
from ..utils import now_iso

router = APIRouter(prefix="/auth", tags=["auth"])


def _cookie_secure() -> bool:
    return os.environ.get("FORELI_COOKIE_SECURE", "0").lower() in ("1", "true", "yes")


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(),
        max_age=SESSION_DAYS * 24 * 3600,
        path="/",
    )


@router.post("/register")
def register(payload: schemas.Credentials, response: Response, db=Depends(get_db)):
    existing = db.execute("SELECT id FROM users WHERE email = ?", (payload.email,)).fetchone()
    if existing is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    cur = db.execute(
        "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
        (payload.email, hash_password(payload.password), now_iso()),
    )
    token = create_session(db, cur.lastrowid)
    _set_session_cookie(response, token)
    return {"id": cur.lastrowid, "email": payload.email}


@router.post("/login")
def login(payload: schemas.Credentials, response: Response, db=Depends(get_db)):
    row = db.execute("SELECT * FROM users WHERE email = ?", (payload.email,)).fetchone()
    if row is None or not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    token = create_session(db, row["id"])
    _set_session_cookie(response, token)
    return {"id": row["id"], "email": row["email"]}


@router.post("/logout")
def logout(request: Request, response: Response, db=Depends(get_db)):
    token = request.cookies.get(COOKIE_NAME)
    if token:
        db.execute("DELETE FROM sessions WHERE token = ?", (token,))
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(user=Depends(get_current_user)):
    return user
