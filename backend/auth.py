"""Server-side authentication for Foreli (stdlib only).

* Passwords are hashed with PBKDF2-HMAC-SHA256 and a per-user random salt.
  Plaintext passwords are never stored.
* Sessions are opaque bearer tokens persisted in SQLite and delivered to the
  browser as an HttpOnly cookie. Protected API routes are enforced server-side.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Request

from .db import get_db
from .utils import parse_dt

PBKDF2_ITERATIONS = 210_000
SESSION_DAYS = 30
COOKIE_NAME = "foreli_session"


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt_hex, digest_hex = stored.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def create_session(db, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    created = datetime.now()
    expires = created + timedelta(days=SESSION_DAYS)
    db.execute(
        "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (
            token,
            user_id,
            created.isoformat(timespec="seconds"),
            expires.isoformat(timespec="seconds"),
        ),
    )
    return token


RESET_MINUTES = 30


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_reset_token(db, user_id: int) -> str:
    """Create a single-use, expiring reset token; only its hash is stored."""
    token = secrets.token_urlsafe(32)
    now = datetime.now()
    db.execute(
        "INSERT INTO password_resets (user_id, token_hash, expires_at, used, created_at) "
        "VALUES (?, ?, ?, 0, ?)",
        (
            user_id,
            _hash_token(token),
            (now + timedelta(minutes=RESET_MINUTES)).isoformat(timespec="seconds"),
            now.isoformat(timespec="seconds"),
        ),
    )
    return token


def consume_reset_token(db, token: str):
    """Validate and consume a reset token; return user_id or None."""
    row = db.execute(
        "SELECT * FROM password_resets WHERE token_hash = ?", (_hash_token(token),)
    ).fetchone()
    if row is None or row["used"]:
        return None
    expires = parse_dt(row["expires_at"])
    if expires is None or expires < datetime.now():
        return None
    db.execute("UPDATE password_resets SET used = 1 WHERE id = ?", (row["id"],))
    return row["user_id"]


def get_current_user(request: Request, db=Depends(get_db)):
    """FastAPI dependency: resolve the authenticated user or raise 401."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    row = db.execute("SELECT * FROM sessions WHERE token = ?", (token,)).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    expires = parse_dt(row["expires_at"])
    if expires is None or expires < datetime.now():
        raise HTTPException(status_code=401, detail="Session expired")
    user = db.execute(
        "SELECT id, email, created_at FROM users WHERE id = ?", (row["user_id"],)
    ).fetchone()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return dict(user)
