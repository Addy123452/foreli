"""Prediction endpoints for the Foreli API."""
import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import schemas
from ..db import get_db
from ..domains import UnsupportedDomain, domain_catalog, resolve_domain
from ..engine import refresh_predictions
from ..utils import now_iso, parse_dt

router = APIRouter(prefix="/predictions", tags=["predictions"])

ORDER_BY = "CASE risk_level WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, created_at DESC"


def _from_row(row) -> dict:
    d = dict(row)
    d["factors"] = json.loads(d.get("factors") or "[]")
    d["related_task_ids"] = json.loads(d.get("related_task_ids") or "[]")
    return d


def _list(db, status: str):
    if status == "all":
        sql = f"SELECT * FROM predictions ORDER BY {ORDER_BY}"
        rows = db.execute(sql).fetchall()
    else:
        sql = f"SELECT * FROM predictions WHERE status = ? ORDER BY {ORDER_BY}"
        rows = db.execute(sql, (status,)).fetchall()
    return [_from_row(r) for r in rows]


@router.get("", response_model=List[schemas.Prediction])
def list_predictions(
    status: str = Query(default="active"),
    domain: str = Query(default="personal"),
    db=Depends(get_db),
):
    if status not in ("active", "resolved", "all"):
        raise HTTPException(status_code=400, detail="status must be one of: active, resolved, all")
    try:
        resolve_domain(domain)
    except UnsupportedDomain as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    refresh_predictions(db)
    return _list(db, status)


@router.post("/refresh", response_model=List[schemas.Prediction])
def refresh(db=Depends(get_db)):
    refresh_predictions(db)
    return _list(db, "active")


@router.get("/domains")
def list_domains():
    """List implemented prediction domains and explicitly unsupported ones."""
    return domain_catalog()


@router.get("/analytics")
def analytics(db=Depends(get_db)):
    """Prediction analytics computed from stored predictions (real data).

    No values are fabricated: with no feedback recorded, accuracy is ``None``.
    """
    rows = db.execute("SELECT * FROM predictions").fetchall()
    total = len(rows)
    active = resolved = 0
    by_type = {}
    by_risk = {"low": 0, "medium": 0, "high": 0}
    resolve_hours = []
    feedback = {"accurate": 0, "partial": 0, "inaccurate": 0}

    for r in rows:
        status = r["status"]
        if status == "active":
            active += 1
        elif status == "resolved":
            resolved += 1

        by_risk[r["risk_level"]] = by_risk.get(r["risk_level"], 0) + 1

        bucket = by_type.setdefault(r["type"], {"total": 0, "active": 0, "resolved": 0})
        bucket["total"] += 1
        if status in ("active", "resolved"):
            bucket[status] += 1

        if status == "resolved" and r["resolved_at"]:
            created = parse_dt(r["created_at"])
            resolved_at = parse_dt(r["resolved_at"])
            if created and resolved_at:
                resolve_hours.append((resolved_at - created).total_seconds() / 3600.0)

        if r["feedback"] in feedback:
            feedback[r["feedback"]] += 1

    feedback_total = sum(feedback.values())
    avg_hours = round(sum(resolve_hours) / len(resolve_hours), 2) if resolve_hours else None
    accuracy = round(feedback["accurate"] / feedback_total, 3) if feedback_total else None

    return {
        "generated_at": now_iso(),
        "total": total,
        "active": active,
        "resolved": resolved,
        "by_type": by_type,
        "by_risk": by_risk,
        "resolution": {"resolved": len(resolve_hours), "avg_hours": avg_hours},
        "feedback": {**feedback, "total": feedback_total, "accuracy": accuracy},
        "note": (
            "Computed from stored predictions. Feedback-based accuracy requires "
            "user feedback; none is fabricated."
        ),
    }


@router.get("/{prediction_id}", response_model=schemas.Prediction)
def get_prediction(prediction_id: int, db=Depends(get_db)):
    row = db.execute("SELECT * FROM predictions WHERE id = ?", (prediction_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Prediction {prediction_id} not found")
    return _from_row(row)


@router.post("/{prediction_id}/feedback", response_model=schemas.Prediction)
def submit_feedback(prediction_id: int, payload: schemas.FeedbackIn, db=Depends(get_db)):
    """Record user feedback (accurate / partial / inaccurate) for a prediction.

    This is user feedback only; it does not retrain any model.
    """
    row = db.execute("SELECT * FROM predictions WHERE id = ?", (prediction_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Prediction {prediction_id} not found")
    if payload.outcome:
        db.execute(
            "UPDATE predictions SET feedback = ?, actual_outcome = ? WHERE id = ?",
            (payload.feedback, payload.outcome, prediction_id),
        )
    else:
        db.execute(
            "UPDATE predictions SET feedback = ? WHERE id = ?",
            (payload.feedback, prediction_id),
        )
    row = db.execute("SELECT * FROM predictions WHERE id = ?", (prediction_id,)).fetchone()
    return _from_row(row)
