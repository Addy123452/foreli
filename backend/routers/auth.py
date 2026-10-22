"""Authentication endpoints (register / login / logout / me / password reset)."""
import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from .. import schemas
from ..auth import (
    COOKIE_NAME,
    SESSION_DAYS,
    consume_reset_token,
    create_reset_token,
    create_session,
    get_current_user,
    hash_password,
    verify_password,
)
from ..db import get_db
from ..utils import now_iso

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger("foreli")


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


def _is_local_request(request: Request) -> bool:
    client = request.client.host if request.client else ""
    return client in ("127.0.0.1", "::1", "localhost")


@router.post("/forgot")
def forgot(payload: schemas.ForgotIn, request: Request, db=Depends(get_db)):
    """Generate a reset link.

    Email delivery is not configured, so the link is written to the server log.
    For local requests (or when FORELI_DEV_RESET_TOKENS=1) the link is also
    returned, so a local user can complete the reset without an email service.
    The response never reveals whether an account exists for other clients.
    """
    row = db.execute("SELECT id FROM users WHERE email = ?", (payload.email,)).fetchone()
    result = {
        "ok": True,
        "message": "If an account exists for that email, a reset link has been generated.",
    }
    if row is not None:
        token = create_reset_token(db, row["id"])
        base = str(request.base_url).rstrip("/")
        reset_url = f"{base}/reset.html?token={token}"
        logger.info("Password reset link: %s", reset_url)
        if _is_local_request(request) or os.environ.get("FORELI_DEV_RESET_TOKENS") == "1":
            result["reset_url"] = reset_url
            result["message"] = "Reset link generated."
    return result


@router.post("/reset")
def reset(payload: schemas.ResetIn, response: Response, db=Depends(get_db)):
    """Complete a password reset with a valid single-use token."""
    user_id = consume_reset_token(db, payload.token)
    if user_id is None:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link.")
    db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (hash_password(payload.password), user_id),
    )
    # Invalidate all existing sessions for this user.
    db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True, "message": "Password updated. Please sign in."}
