"""Foreli backend entry point.

Run locally with (from the project root):

    python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

The API lives under ``/api`` and the static frontend is served from the same
origin at ``/``, ``/index.html``, and ``/dashboard``.
"""
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from . import db
from .auth import get_current_user
from .routers import auth, live, predictions, tasks
from .utils import parse_dt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("foreli")

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    logger.info("Foreli database initialized at %s", db.DB_PATH)
    yield


app = FastAPI(
    title="Foreli API",
    version="0.1.0",
    description="Local API for the Foreli personal prediction system.",
    lifespan=lifespan,
)

_origins = [o.strip() for o in os.environ.get("FORELI_CORS_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["*"],
    allow_credentials=bool(_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(tasks.router, prefix="/api", dependencies=[Depends(get_current_user)])
app.include_router(predictions.router, prefix="/api", dependencies=[Depends(get_current_user)])
app.include_router(live.router, prefix="/api")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled error: %s", exc.__class__.__name__, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/api/health")
def health():
    db_ok = True
    try:
        conn = db.connect()
        conn.execute("SELECT 1").fetchone()
        conn.close()
    except Exception:
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "service": "foreli",
        "version": app.version,
        "database": "connected" if db_ok else "error",
        "time": datetime.now().isoformat(timespec="seconds"),
    }


@app.get("/api/stats")
def stats(db_conn=Depends(db.get_db)):
    now = datetime.now()
    today = now.date()
    next7 = now + timedelta(days=7)

    by_status = {"todo": 0, "in_progress": 0, "done": 0, "cancelled": 0}
    by_priority = {"low": 0, "medium": 0, "high": 0, "urgent": 0}
    overdue = due_today = due_next7 = completed_today = 0

    rows = db_conn.execute("SELECT * FROM tasks").fetchall()
    for r in rows:
        s = r["status"]
        p = r["priority"]
        by_status[s] = by_status.get(s, 0) + 1
        by_priority[p] = by_priority.get(p, 0) + 1

        due = parse_dt(r["due_at"])
        if due:
            if s in ("todo", "in_progress") and due < now:
                overdue += 1
            if due.date() == today:
                due_today += 1
            if now <= due <= next7:
                due_next7 += 1

        if s == "done":
            cd = parse_dt(r["completed_at"])
            if cd and cd.date() == today:
                completed_today += 1

    return {
        "total": len(rows),
        "active": by_status["todo"] + by_status["in_progress"],
        "by_status": by_status,
        "by_priority": by_priority,
        "overdue": overdue,
        "due_today": due_today,
        "due_next7": due_next7,
        "completed_today": completed_today,
    }


# --- Static frontend (served so the whole app runs from one origin) ---

@app.get("/", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
def serve_index():
    return FileResponse(ROOT / "index.html")


@app.get("/dashboard", include_in_schema=False)
@app.get("/dashboard.html", include_in_schema=False)
def serve_dashboard():
    return FileResponse(ROOT / "dashboard.html")


@app.get("/login", include_in_schema=False)
@app.get("/login.html", include_in_schema=False)
def serve_login():
    return FileResponse(ROOT / "login.html")


@app.get("/register", include_in_schema=False)
@app.get("/register.html", include_in_schema=False)
def serve_register():
    return FileResponse(ROOT / "register.html")


@app.get("/assets/{file_path:path}", include_in_schema=False)
def serve_assets(file_path: str):
    target = (ASSETS / file_path).resolve()
    if not target.is_relative_to(ASSETS.resolve()) or not target.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(target)
