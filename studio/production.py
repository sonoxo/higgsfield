"""Editing, sequencing, production exports and render queue for Cinema Studio."""
from __future__ import annotations

import json
import shutil
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api", tags=["production"])
_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cinema-render")
_lock = threading.Lock()


class ShotPatch(BaseModel):
    prompt: str | None = Field(default=None, min_length=1, max_length=4000)
    camera: str | None = Field(default=None, max_length=120)
    duration: float | None = Field(default=None, ge=0.5, le=60)
    asset_id: str | None = None


class SequenceIn(BaseModel):
    shot_ids: list[str] = Field(min_length=1, max_length=500)


def core():
    from studio import server
    return server


@router.patch("/projects/{project_id}/shots/{shot_id}")
def edit_shot(project_id: str, shot_id: str, body: ShotPatch):
    s = core()
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(400, "No fields supplied")
    with s.connect() as db:
        s.require_project(db, project_id)
        if not db.execute("SELECT 1 FROM shots WHERE id=? AND project_id=?",
                          (shot_id, project_id)).fetchone():
            raise HTTPException(404, "Shot not found")
        if "asset_id" in fields and fields["asset_id"] is not None:
            if not db.execute("SELECT 1 FROM assets WHERE id=? AND project_id=?",
                              (fields["asset_id"], project_id)).fetchone():
                raise HTTPException(400, "Asset not part of project")
        for key, value in fields.items():
            db.execute(f"UPDATE shots SET {key}=? WHERE id=? AND project_id=?",
                       (value, shot_id, project_id))
        row = db.execute("SELECT * FROM shots WHERE id=?", (shot_id,)).fetchone()
        return dict(row)


@router.put("/projects/{project_id}/sequence")
def reorder(project_id: str, body: SequenceIn):
    s = core()
    with s.connect() as db:
        s.require_project(db, project_id)
        current = [r[0] for r in db.execute("SELECT id FROM shots WHERE project_id=?", (project_id,))]
        if len(body.shot_ids) != len(current) or set(body.shot_ids) != set(current):
            raise HTTPException(400, "Provide each existing shot exactly once")
        for position, shot_id in enumerate(body.shot_ids):
            db.execute("UPDATE shots SET position=? WHERE id=? AND project_id=?",
                       (position, shot_id, project_id))
    return {"shot_ids": body.shot_ids}


@router.get("/projects/{project_id}/export")
def export_project(project_id: str):
    s = core()
    project = s.project(project_id)
    # Machine-readable EDL-like export; not an AAF or conformable EDL.
    at = 0.0
    timeline = []
    for shot in project["shots"]:
        timeline.append({"shot_id": shot["id"], "start_seconds": at,
                         "end_seconds": round(at + shot["duration"], 3),
                         "prompt": shot["prompt"], "camera": shot["camera"],
                         "asset_id": shot["asset_id"]})
        at = round(at + shot["duration"], 3)
    return {"format": "gpt-doug-cinema-json-v1", "project": project,
            "timeline": timeline, "runtime_seconds": round(at, 3)}


def _do_render(project_id: str, render_id: str):
    """Reuse existing local FFmpeg renderer; mirror its outcome on the queue record."""
    s = core()
    try:
        result = s.render_project(project_id)
        with s.connect() as db:
            db.execute("UPDATE renders SET status='completed', detail=? WHERE id=?",
                       (result["id"], render_id))
    except Exception as exc:
        with s.connect() as db:
            db.execute("UPDATE renders SET status='failed', detail=? WHERE id=?",
                       (str(exc)[:500], render_id))


@router.post("/projects/{project_id}/render-jobs", status_code=202)
def enqueue_render(project_id: str):
    s = core()
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise HTTPException(503, "FFmpeg and ffprobe required")
    with s.connect() as db:
        s.require_project(db, project_id)
        shots = list(db.execute("SELECT asset_id FROM shots WHERE project_id=?", (project_id,)))
        if not shots or any(not x["asset_id"] for x in shots):
            raise HTTPException(400, "All shots must be assigned media")
        # One outstanding render per project in this single-process queue.
        busy = db.execute("SELECT 1 FROM renders WHERE project_id=? AND status IN ('queued','processing')",
                          (project_id,)).fetchone()
        if busy:
            raise HTTPException(409, "Project already has an outstanding render")
        render_id = uuid.uuid4().hex
        db.execute("INSERT INTO renders VALUES (?,?,?,?,?)",
                   (render_id, project_id, "queued", None, s.now()))
    _pool.submit(_do_render, project_id, render_id)
    return {"id": render_id, "status": "queued",
            "status_url": f"/api/projects/{project_id}/render-jobs/{render_id}"}


@router.get("/projects/{project_id}/render-jobs/{render_id}")
def render_status(project_id: str, render_id: str):
    s = core()
    with s.connect() as db:
        row = db.execute("SELECT * FROM renders WHERE project_id=? AND id=?",
                         (project_id, render_id)).fetchone()
    if not row:
        raise HTTPException(404, "Render job not found")
    value = dict(row)
    if value["status"] == "completed" and value["detail"]:
        value["download_url"] = f"/api/projects/{project_id}/renders/{value['detail']}.mp4"
    return value
