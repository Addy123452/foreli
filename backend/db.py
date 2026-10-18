"""SQLite persistence for Foreli.

A small, explicit migration system based on ``PRAGMA user_version`` keeps the
schema easy to evolve without an external migration framework. The database
file lives next to this module at ``backend/foreli.db``.
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "foreli.db"

# Each entry is a migration applied in order. Entry index 0 -> user_version 1,
# entry index 1 -> user_version 2, and so on.
MIGRATIONS = [
    # v1: tasks
    """
    CREATE TABLE IF NOT EXISTS tasks (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        title             TEXT    NOT NULL,
        description       TEXT,
        status            TEXT    NOT NULL DEFAULT 'todo',
        priority          TEXT    NOT NULL DEFAULT 'medium',
        due_at            TEXT,
        scheduled_at      TEXT,
        estimated_minutes INTEGER,
        tags              TEXT    NOT NULL DEFAULT '[]',
        created_at        TEXT    NOT NULL,
        updated_at        TEXT    NOT NULL,
        completed_at      TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
    CREATE INDEX IF NOT EXISTS idx_tasks_due_at ON tasks(due_at);
    """,
    # v2: predictions
    """
    CREATE TABLE IF NOT EXISTS predictions (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        type              TEXT    NOT NULL,
        title             TEXT    NOT NULL,
        risk_level        TEXT    NOT NULL DEFAULT 'medium',
        probability       REAL,
        explanation       TEXT    NOT NULL,
        factors           TEXT    NOT NULL DEFAULT '[]',
        recommendation    TEXT,
        horizon           TEXT,
        related_task_ids  TEXT    NOT NULL DEFAULT '[]',
        fingerprint       TEXT    NOT NULL,
        status            TEXT    NOT NULL DEFAULT 'active',
        actual_outcome    TEXT,
        feedback          TEXT,
        created_at        TEXT    NOT NULL,
        resolved_at       TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_predictions_status ON predictions(status);
    CREATE INDEX IF NOT EXISTS idx_predictions_fingerprint ON predictions(fingerprint);
    """,
    # v3: authentication (users + server-side sessions)
    """
    CREATE TABLE IF NOT EXISTS users (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        email         TEXT    NOT NULL UNIQUE,
        password_hash TEXT    NOT NULL,
        created_at    TEXT    NOT NULL
    );
    CREATE TABLE IF NOT EXISTS sessions (
        token      TEXT    PRIMARY KEY,
        user_id    INTEGER NOT NULL,
        created_at TEXT    NOT NULL,
        expires_at TEXT    NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
    """,
]


def connect() -> sqlite3.Connection:
    # check_same_thread=False: FastAPI may enter this sync-generator dependency
    # and run the endpoint/exit on different threadpool threads. Each request
    # gets its own connection, so cross-thread use is sequential, not concurrent.
    conn = sqlite3.connect(
        DB_PATH,
        detect_types=sqlite3.PARSE_DECLTYPES,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Apply any pending migrations and set WAL journaling."""
    conn = connect()
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        current = conn.execute("PRAGMA user_version").fetchone()[0]
        for index, script in enumerate(MIGRATIONS, start=1):
            if index > current:
                conn.executescript(script)
                conn.execute(f"PRAGMA user_version = {index}")
        conn.commit()
    finally:
        conn.close()


def get_db():
    """FastAPI dependency yielding a connection with commit/rollback handling."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
