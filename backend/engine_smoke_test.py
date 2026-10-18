"""Smoke test for the Foreli prediction engine (no pytest dependency).

Run from the project root:

    python -m backend.engine_smoke_test

Uses a fixed reference time so results are deterministic, and asserts every
prediction type fires with the expected risk level and (where calibrated) the
expected probability.
"""
from datetime import datetime

from backend.engine import _build_predictions

NOW = datetime(2026, 10, 16, 12, 0, 0)


def task(id, title, status="todo", priority="medium", due=None, est=None,
         completed=None, created="2026-10-01T09:00:00"):
    return {
        "id": id, "title": title, "description": None, "status": status,
        "priority": priority, "due_at": due, "scheduled_at": None,
        "estimated_minutes": est, "tags": [], "created_at": created,
        "updated_at": created, "completed_at": completed,
    }


def build():
    return [
        # Daily overload + schedule conflict (3 tasks due today).
        task(1, "A", due="2026-10-16T18:00:00", est=240, priority="high"),
        task(2, "B", due="2026-10-16T20:00:00", est=240),
        task(3, "C", due="2026-10-16T22:00:00", est=240),
        # Delay: overdue.
        task(4, "Overdue", due="2026-10-13T10:00:00", priority="high"),
        # Delay: stalled, no deadline, urgent, open > 1 week.
        task(5, "Stalled", priority="urgent", created="2026-09-01T09:00:00"),
        # Missed: three late completions (all > 1 week ago).
        task(6, "late1", status="done", due="2026-09-01T10:00:00", completed="2026-09-02T10:00:00"),
        task(7, "late2", status="done", due="2026-09-03T10:00:00", completed="2026-09-04T10:00:00"),
        task(8, "late3", status="done", due="2026-09-05T10:00:00", completed="2026-09-06T10:00:00"),
        # Slowdown: 3 completions last week, 1 this week.
        task(9, "lw1", status="done", completed="2026-10-03T10:00:00"),
        task(10, "lw2", status="done", completed="2026-10-04T10:00:00"),
        task(11, "lw3", status="done", completed="2026-10-05T10:00:00"),
        task(12, "tw1", status="done", completed="2026-10-15T10:00:00"),
        # Weekly workload: large estimates spread over the next few days.
        task(13, "W1", due="2026-10-17T10:00:00", est=600),
        task(14, "W2", due="2026-10-18T10:00:00", est=600),
        task(15, "W3", due="2026-10-19T10:00:00", est=600),
    ]


def main():
    preds = _build_predictions(build(), NOW)
    by_type = {}
    for p in preds:
        by_type.setdefault(p["type"], []).append(p)

    print("Generated predictions:")
    for t in sorted(by_type):
        for p in by_type[t]:
            print(f"  [{t}] risk={p['risk_level']} prob={p['probability']} :: {p['title']}")

    types = set(by_type)
    expected = {"overload", "workload", "conflict", "delay", "missed", "slowdown"}
    assert expected <= types, f"Missing types: {expected - types}"

    # Overload: 720 min today -> high.
    assert any(p["risk_level"] == "high" for p in by_type["overload"]), "overload should be high"
    # Workload: 2520 min this week -> medium.
    assert all(p["risk_level"] == "medium" for p in by_type["workload"]), "workload should be medium"
    # Conflict: A/B and B/C overlap ~50% -> high.
    assert any(p["risk_level"] == "high" for p in by_type["conflict"]), "conflict should be high"
    # Missed: 3/3 late -> probability 1.0, high.
    missed = by_type["missed"][0]
    assert missed["probability"] == 1.0, f"missed prob {missed['probability']}"
    assert missed["risk_level"] == "high", "missed should be high"
    # Slowdown: 1 vs 3 -> medium, no probability.
    slow = by_type["slowdown"][0]
    assert slow["risk_level"] == "medium", "slowdown should be medium"
    assert slow["probability"] is None, "slowdown should not invent a probability"
    # Delay: overdue + stalled both present.
    assert len(by_type["delay"]) == 2, f"expected 2 delay predictions, got {len(by_type['delay'])}"

    print("\nAll engine assertions passed.")


if __name__ == "__main__":
    main()
