"""Task CRUD endpoints for the Foreli API."""
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from .. import schemas
from ..db import get_db
from ..utils import now_iso

router = APIRouter(prefix="/tasks", tags=["tasks"])

VALID_STATUS = {"todo", "in_progress", "done", "cancelled"}
VALID_PRIORITY = {"low", "medium", "high", "urgent"}
# Fields that may be cleared but never set to NULL.
NON_NULLABLE = {"title", "status", "priority"}


def _from_row(row) -> dict:
    d = dict(row)
    d["tags"] = json.loads(d.get("tags") or "[]")
    return d


@router.get("", response_model=List[schemas.Task])
def list_tasks(
    q: Optional[str] = Query(default=None, max_length=200),
    status: Optional[str] = Query(default=None),
    priority: Optional[str] = Query(default=None),
    db=Depends(get_db),
):
    clauses = []
    params = []
    if q:
        clauses.append("(title LIKE ? OR COALESCE(description, '') LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like])
    if status:
        if status not in VALID_STATUS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{status}'. Allowed: {sorted(VALID_STATUS)}",
            )
        clauses.append("status = ?")
        params.append(status)
    if priority:
        if priority not in VALID_PRIORITY:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid priority '{priority}'. Allowed: {sorted(VALID_PRIORITY)}",
            )
        clauses.append("priority = ?")
        params.append(priority)

    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = (
        "SELECT * FROM tasks" + where
        + " ORDER BY (due_at IS NULL), due_at ASC,"
        " CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,"
        " created_at DESC"
    )
    rows = db.execute(sql, params).fetchall()
    return [_from_row(r) for r in rows]


@router.post("", response_model=schemas.Task, status_code=201)
def create_task(payload: schemas.TaskCreate, db=Depends(get_db)):
    now = now_iso()
    cur = db.execute(
        """INSERT INTO tasks
           (title, description, status, priority, due_at, scheduled_at,
            estimated_minutes, tags, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            payload.title,
            payload.description,
            payload.status,
            payload.priority,
            payload.due_at,
            payload.scheduled_at,
            payload.estimated_minutes,
            json.dumps(payload.tags),
            now,
            now,
        ),
    )
    row = db.execute("SELECT * FROM tasks WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _from_row(row)


@router.get("/{task_id}", response_model=schemas.Task)
def get_task(task_id: int, db=Depends(get_db)):
    row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return _from_row(row)


@router.patch("/{task_id}", response_model=schemas.Task)
def update_task(task_id: int, payload: schemas.TaskUpdate, db=Depends(get_db)):
    row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    for key in NON_NULLABLE:
        if key in updates and updates[key] is None:
            raise HTTPException(status_code=422, detail=f"Field '{key}' cannot be null")

    set_parts = []
    params = []
    for key, value in updates.items():
        if key in ("id", "created_at", "updated_at", "completed_at"):
            continue
        if key == "tags":
            value = json.dumps(value or [])
        set_parts.append(f"{key} = ?")
        params.append(value)

    if "status" in updates:
        if updates["status"] == "done":
            set_parts.append("completed_at = ?")
            params.append(now_iso())
        else:
            set_parts.append("completed_at = NULL")

    set_parts.append("updated_at = ?")
    params.append(now_iso())
    params.append(task_id)

    db.execute(f"UPDATE tasks SET {', '.join(set_parts)} WHERE id = ?", params)
    row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return _from_row(row)


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: int, db=Depends(get_db)):
    cur = db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")


@router.post("/{task_id}/toggle", response_model=schemas.Task)
def toggle_task(task_id: int, db=Depends(get_db)):
    row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    new_status = "todo" if row["status"] == "done" else "done"
    completed_at = now_iso() if new_status == "done" else None
    db.execute(
        "UPDATE tasks SET status = ?, completed_at = ?, updated_at = ? WHERE id = ?",
        (new_status, completed_at, now_iso(), task_id),
    )
    row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    return _from_row(row)
