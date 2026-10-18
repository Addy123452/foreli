"""Foreli prediction engine.

Transparent rule-based logic plus statistical baselines, derived from real task
data. No arbitrary confidence values: ``probability`` is only set when there is
a calibrated statistical basis (e.g. a historical late-completion rate with a
minimum sample size). Every prediction stores its explanation, contributing
factors, and a recommended preventive action.
"""
import hashlib
import json
from datetime import datetime, timedelta

from .utils import now_iso, parse_dt

ACTIVE = ("todo", "in_progress")

# Daily capacity thresholds (minutes). 480 = 8h, 720 = 12h.
DAILY_OVERLOAD_MEDIUM = 480
DAILY_OVERLOAD_HIGH = 720
# Weekly capacity thresholds (minutes). 2400 = 40h, 3600 = 60h.
WEEKLY_OVERLOAD_MEDIUM = 2400
WEEKLY_OVERLOAD_HIGH = 3600
# Minimum sample sizes before making statistical claims.
MIN_SAMPLES_LATE = 3
MIN_SAMPLES_SLOWDOWN = 3
# Cap the number of per-task delay predictions to avoid noise.
MAX_DELAY_PREDICTIONS = 10


def _fp(*parts) -> str:
    """Stable fingerprint for a prediction so refreshes reconcile instead of duplicate."""
    raw = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _hours(mins: int) -> str:
    return f"{mins / 60:.1f} hours"


def _build_predictions(tasks, now):
    preds = []
    today = now.date()

    active = [t for t in tasks if t["status"] in ACTIVE]

    # Group active, future-dated tasks by their due date.
    by_day = {}
    for t in active:
        d = parse_dt(t["due_at"])
        if d and d.date() >= today:
            by_day.setdefault(d.date().isoformat(), []).append(t)

    # --- Daily overload (deadline / task-overload risk) ---
    for key in sorted(by_day):
        day_tasks = by_day[key]
        with_est = [t for t in day_tasks if t["estimated_minutes"]]
        est_total = sum(t["estimated_minutes"] for t in with_est)
        if len(day_tasks) >= 2 and with_est and est_total >= DAILY_OVERLOAD_MEDIUM:
            risk = "high" if est_total >= DAILY_OVERLOAD_HIGH else "medium"
            ids = sorted(t["id"] for t in day_tasks)
            preds.append({
                "type": "overload",
                "title": f"Overloaded day on {key}",
                "risk_level": risk,
                "probability": None,
                "explanation": (
                    f"{len(day_tasks)} active tasks are due on {key} with an estimated "
                    f"{_hours(est_total)} of work."
                ),
                "factors": [
                    f"{len(day_tasks)} tasks due the same day",
                    f"Estimated {est_total} minutes of work",
                    f"Exceeds the {DAILY_OVERLOAD_MEDIUM // 60}-hour daily capacity",
                ],
                "recommendation": "Move the largest task to a lighter day or break it into smaller pieces.",
                "horizon": key,
                "related_task_ids": ids,
                "fingerprint": _fp("overload", key, ids),
            })

    # --- Unrealistic weekly workload ---
    week_tasks = []
    week_total = 0
    for t in active:
        d = parse_dt(t["due_at"])
        if d and today <= d.date() <= today + timedelta(days=7) and t["estimated_minutes"]:
            week_tasks.append(t)
            week_total += t["estimated_minutes"]
    if len(week_tasks) >= 3 and week_total >= WEEKLY_OVERLOAD_MEDIUM:
        risk = "high" if week_total >= WEEKLY_OVERLOAD_HIGH else "medium"
        preds.append({
            "type": "workload",
            "title": "Heavy workload over the next 7 days",
            "risk_level": risk,
            "probability": None,
            "explanation": (
                f"{len(week_tasks)} active tasks with estimates total {_hours(week_total)} "
                f"across the next 7 days."
            ),
            "factors": [
                f"{len(week_tasks)} tasks due this week",
                f"Estimated {week_total} minutes total",
            ],
            "recommendation": "Reschedule or delegate lower-priority tasks to spread the load.",
            "horizon": "next 7 days",
            "related_task_ids": sorted(t["id"] for t in week_tasks),
            "fingerprint": _fp("workload", sorted(t["id"] for t in week_tasks)),
        })

    # --- Schedule conflicts (same-day overlapping work windows) ---
    for key in sorted(by_day):
        day_tasks = [t for t in by_day[key] if t["due_at"] and t["estimated_minutes"]]
        if len(day_tasks) < 2:
            continue

        def _window(t):
            end = parse_dt(t["due_at"])
            start = end - timedelta(minutes=t["estimated_minutes"])
            return (start, end, t)

        windows = sorted((_window(t) for t in day_tasks), key=lambda w: w[0])
        for i in range(len(windows)):
            s1, e1, a = windows[i]
            for j in range(i + 1, len(windows)):
                s2, e2, b = windows[j]
                if s1 < e2 and s2 < e1:  # overlap
                    overlap = min(e1, e2) - max(s1, s2)
                    longer = max(e1 - s1, e2 - s2)
                    frac = overlap.total_seconds() / longer.total_seconds() if longer else 0
                    risk = "high" if frac >= 0.5 else "medium"
                    ids = sorted([a["id"], b["id"]])
                    preds.append({
                        "type": "conflict",
                        "title": f"Scheduling conflict on {key}",
                        "risk_level": risk,
                        "probability": None,
                        "explanation": (
                            f"'{a['title']}' and '{b['title']}' overlap on {key} "
                            f"(estimated work windows overlap by {int(frac * 100)}%)."
                        ),
                        "factors": [
                            f"'{a['title']}' and '{b['title']}' share the same window",
                            f"Overlap ~{int(frac * 100)}% of a task's duration",
                        ],
                        "recommendation": "Stagger their start times or move one to a different day.",
                        "horizon": key,
                        "related_task_ids": ids,
                        "fingerprint": _fp("conflict", key, ids),
                    })
                    break  # one conflict per task is enough to avoid noise

    # --- Delay risk (overdue or stalled tasks) ---
    delay_candidates = []
    for t in active:
        d = parse_dt(t["due_at"])
        if d and d < now:
            overdue_days = (now.date() - d.date()).days
            delay_candidates.append((0, overdue_days, t))
        elif not d and t["priority"] in ("urgent", "high"):
            created = parse_dt(t["created_at"])
            if created and created < now - timedelta(days=7):
                delay_candidates.append((1, 0, t))

    # Most severe first: overdue before stalled; then by days overdue desc, priority.
    def _delay_key(item):
        kind, days, t = item
        prio = {"urgent": 0, "high": 1, "medium": 2, "low": 3}[t["priority"]]
        return (kind, -days, prio)

    delay_candidates.sort(key=_delay_key)
    for kind, days, t in delay_candidates[:MAX_DELAY_PREDICTIONS]:
        if kind == 0:
            risk = "high" if days >= 2 or t["priority"] in ("urgent", "high") else "medium"
            preds.append({
                "type": "delay",
                "title": f"'{t['title']}' is overdue",
                "risk_level": risk,
                "probability": None,
                "explanation": (
                    f"This task was due on {parse_dt(t['due_at']).strftime('%Y-%m-%d %H:%M')} "
                    f"and is still active."
                ),
                "factors": [f"Overdue by {days} day(s)", f"Priority: {t['priority']}"],
                "recommendation": "Reschedule it to a concrete new deadline or mark it done.",
                "horizon": "today",
                "related_task_ids": [t["id"]],
                "fingerprint": _fp("delay", t["id"]),
            })
        else:
            preds.append({
                "type": "delay",
                "title": f"'{t['title']}' has no deadline",
                "risk_level": "medium",
                "probability": None,
                "explanation": "This high/urgent task has no due date and has been open for over a week.",
                "factors": ["No due date set", f"Priority: {t['priority']}"],
                "recommendation": "Assign a due date so Foreli can schedule it.",
                "horizon": "this week",
                "related_task_ids": [t["id"]],
                "fingerprint": _fp("delay", "nodeadline", t["id"]),
            })

    # --- Repeated missed deadlines (calibrated statistical baseline) ---
    completed_with_deadline = [
        t for t in tasks
        if t["status"] == "done" and t["completed_at"] and t["due_at"]
    ]
    if len(completed_with_deadline) >= MIN_SAMPLES_LATE:
        late = []
        for t in completed_with_deadline:
            done_at = parse_dt(t["completed_at"])
            due_at = parse_dt(t["due_at"])
            if done_at and due_at and done_at > due_at:
                late.append(t)
        late_rate = len(late) / len(completed_with_deadline)
        if late_rate >= 0.5:
            risk = "high" if late_rate >= 0.7 else "medium"
            preds.append({
                "type": "missed",
                "title": "Deadlines are frequently missed",
                "risk_level": risk,
                "probability": round(late_rate, 3),
                "explanation": (
                    f"{len(late)} of the last {len(completed_with_deadline)} completed tasks with "
                    f"deadlines were finished after their due date."
                ),
                "factors": [
                    f"Historical late rate: {late_rate:.0%}",
                    f"Sample: {len(completed_with_deadline)} completed tasks with deadlines",
                ],
                "recommendation": "Pad estimates by 25–50% and review daily workload before committing.",
                "horizon": "ongoing",
                "related_task_ids": [],
                "fingerprint": _fp("missed"),
            })

    # --- Completion slowdown (this week vs last week) ---
    def _completed_between(start, end):
        count = 0
        for t in tasks:
            if t["status"] != "done" or not t["completed_at"]:
                continue
            cd = parse_dt(t["completed_at"])
            if cd and start <= cd < end:
                count += 1
        return count

    week = timedelta(days=7)
    last_week = _completed_between(now - 2 * week, now - week)
    this_week = _completed_between(now - week, now)
    if last_week >= MIN_SAMPLES_SLOWDOWN and this_week < last_week * 0.5:
        risk = "high" if this_week == 0 else "medium"
        preds.append({
            "type": "slowdown",
            "title": "Completion pace has dropped",
            "risk_level": risk,
            "probability": None,
            "explanation": (
                f"You completed {this_week} task(s) in the last 7 days versus {last_week} "
                f"in the previous 7 days."
            ),
            "factors": [
                f"{last_week} completions last week",
                f"{this_week} completions this week",
            ],
            "recommendation": "Review what changed and reschedule non-essential work.",
            "horizon": "this week",
            "related_task_ids": [],
            "fingerprint": _fp("slowdown"),
        })

    return preds


def refresh_predictions(db):
    """Reconcile predictions against current task data.

    Inserts new predictions and resolves ones whose underlying condition no
    longer holds. Returns ``(inserted, resolved)`` counts.
    """
    now = datetime.now()
    tasks = [dict(r) for r in db.execute("SELECT * FROM tasks").fetchall()]
    for t in tasks:
        t["tags"] = json.loads(t.get("tags") or "[]")

    new_preds = _build_predictions(tasks, now)
    existing = db.execute("SELECT * FROM predictions WHERE status = 'active'").fetchall()
    existing_by_fp = {r["fingerprint"]: r for r in existing}
    new_by_fp = {p["fingerprint"]: p for p in new_preds}

    created_at = now_iso()
    inserted = 0
    for fp, p in new_by_fp.items():
        if fp not in existing_by_fp:
            db.execute(
                """INSERT INTO predictions
                   (type, title, risk_level, probability, explanation, factors,
                    recommendation, horizon, related_task_ids, fingerprint, status,
                    actual_outcome, feedback, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', NULL, NULL, ?)""",
                (
                    p["type"], p["title"], p["risk_level"], p["probability"],
                    p["explanation"], json.dumps(p["factors"]), p["recommendation"],
                    p["horizon"], json.dumps(p["related_task_ids"]), fp, created_at,
                ),
            )
            inserted += 1

    resolved = 0
    for fp, r in existing_by_fp.items():
        if fp not in new_by_fp:
            db.execute(
                "UPDATE predictions SET status = 'resolved', actual_outcome = ?, resolved_at = ? WHERE id = ?",
                ("Risk no longer applies (underlying task data changed).", created_at, r["id"]),
            )
            resolved += 1

    return inserted, resolved
