"""Shared datetime helpers for the Foreli backend.

Convention for this local milestone: timestamps are stored as *naive local*
ISO 8601 strings (e.g. ``2026-10-16T14:00:00``). The server and the browser
run on the same machine, so "today" is consistent between them. A later
hardening milestone should migrate to UTC storage with an explicit timezone.
"""
from datetime import datetime


def now_iso() -> str:
    """Current local time as an ISO 8601 string with second precision."""
    return datetime.now().isoformat(timespec="seconds")


def parse_dt(value):
    """Parse a stored ISO string into a naive datetime, or ``None``."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def normalize_dt(value):
    """Normalize an incoming datetime value to a naive ISO string with seconds.

    Accepts a naive or offset-aware ISO string; offset-aware values are
    converted to the machine's local time. Returns ``None`` for empty input.
    Raises ``ValueError`` for unparseable input.
    """
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt.isoformat(timespec="seconds")
    raise ValueError("datetime must be an ISO 8601 string")
