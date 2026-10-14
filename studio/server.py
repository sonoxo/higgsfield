"""GPT-Doug Cinema Studio API. Run: uvicorn studio.server:app --reload"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

ROOT = Path(os.environ.get("CINEMA_DATA_DIR", "./studio-data")).resolve()
ROOT.mkdir(parents=True, exist_ok=True)
DB = ROOT / "projects.sqlite3"
UPLOAD_LIMIT = 500 * 1024 * 1024
VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/webm"}
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
app = FastAPI(title="GPT-Doug Cinema Studio", version="0.1.0")


def connect():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""CREATE TABLE IF NOT EXISTS projects (
       id TEXT PRIMARY KEY, name TEXT NOT NULL, created TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS shots (
       id TEXT PRIMARY KEY, project_id TEXT NOT NULL, position INTEGER NOT NULL,
       prompt TEXT NOT NULL, camera TEXT NOT NULL, duration REAL NOT NULL,
       asset_id TEXT, FOREIGN KEY(project_id) REFERENCES projects(id))""")
    db.execute("""CREATE TABLE IF NOT EXISTS assets (
       id TEXT PRIMARY KEY, project_id TEXT NOT NULL, filename TEXT NOT NULL,
       mime TEXT NOT NULL, created TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS renders (
       id TEXT PRIMARY KEY, project_id TEXT NOT NULL, status TEXT NOT NULL,
       detail TEXT, created TEXT NOT NULL)""")
    db.commit()
    return db


def now():
    return datetime.now(timezone.utc).isoformat()


def require_project(db, project_id):
    if not db.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone():
        raise HTTPException(404, "Project not found")


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ShotIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    camera: str = Field(default="cinematic dolly", max_length=120)
    duration: float = Field(default=5.0, ge=0.5, le=60)
    asset_id: str | None = None


class PromptIn(BaseModel):
    idea: str = Field(min_length=1, max_length=4000)
    genre: str = Field(default="cinematic", max_length=80)
    mood: str = Field(default="dramatic", max_length=80)
    aspect_ratio: Literal["16:9", "9:16", "1:1", "2.39:1"] = "16:9"


@app.get("/api/health")
def health():
    return {"status": "ok", "ffmpeg": bool(shutil.which("ffmpeg")), "storage": str(ROOT)}


@app.get("/api/projects")
def projects():
    with connect() as db:
        return [dict(x) for x in db.execute("SELECT * FROM projects ORDER BY created DESC")]


@app.post("/api/projects", status_code=201)
def create_project(body: ProjectIn):
    row = {"id": uuid.uuid4().hex, "name": body.name, "created": now()}
    with connect() as db:
        db.execute("INSERT INTO projects VALUES (:id,:name,:created)", row)
    return row


@app.get("/api/projects/{project_id}")
def project(project_id: str):
    with connect() as db:
        require_project(db, project_id)
        p = dict(db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone())
        p["shots"] = [dict(x) for x in db.execute(
            "SELECT * FROM shots WHERE project_id=? ORDER BY position,id", (project_id,))]
        p["assets"] = [dict(x) for x in db.execute(
            "SELECT * FROM assets WHERE project_id=? ORDER BY created DESC", (project_id,))]
        p["renders"] = [dict(x) for x in db.execute(
            "SELECT * FROM renders WHERE project_id=? ORDER BY created DESC", (project_id,))]
    return p


@app.post("/api/projects/{project_id}/shots", status_code=201)
def add_shot(project_id: str, body: ShotIn):
    with connect() as db:
        require_project(db, project_id)
        if body.asset_id and not db.execute(
            "SELECT 1 FROM assets WHERE id=? AND project_id=?", (body.asset_id, project_id)
        ).fetchone():
            raise HTTPException(400, "Asset not found in this project")
        position = db.execute(
            "SELECT COALESCE(MAX(position),-1)+1 FROM shots WHERE project_id=?", (project_id,)
        ).fetchone()[0]
        row = {"id": uuid.uuid4().hex, "project_id": project_id, "position": position, **body.model_dump()}
        db.execute("""INSERT INTO shots (id,project_id,position,prompt,camera,duration,asset_id)
           VALUES (:id,:project_id,:position,:prompt,:camera,:duration,:asset_id)""", row)
    return row


@app.delete("/api/projects/{project_id}/shots/{shot_id}", status_code=204)
def remove_shot(project_id: str, shot_id: str):
    with connect() as db:
        require_project(db, project_id)
        result = db.execute("DELETE FROM shots WHERE id=? AND project_id=?", (shot_id, project_id))
        if result.rowcount == 0:
            raise HTTPException(404, "Shot not found")


@app.post("/api/projects/{project_id}/assets", status_code=201)
async def upload_asset(project_id: str, file: UploadFile = File(...)):
    if file.content_type not in VIDEO_TYPES | IMAGE_TYPES:
        raise HTTPException(415, "Unsupported media MIME type")
    with connect() as db:
        require_project(db, project_id)
    asset_id = uuid.uuid4().hex
    directory = ROOT / "assets" / project_id
    directory.mkdir(parents=True, exist_ok=True)
    ext = { "video/mp4": ".mp4", "video/quicktime": ".mov", "video/webm": ".webm",
            "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp" }[file.content_type]
    dest = directory / (asset_id + ext)
    size = 0
    try:
        with dest.open("wb") as target:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > UPLOAD_LIMIT:
                    raise HTTPException(413, "File exceeds 500 MB")
                target.write(chunk)
        if size == 0:
            raise HTTPException(400, "Empty asset")
        # Check actual media decoding, not only client-reported MIME.
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
            "stream=codec_type", "-of", "csv=p=0", str(dest)],
            capture_output=True, text=True, timeout=30, check=False)
        if probe.returncode or not any(s in probe.stdout for s in ("video",)):
            raise HTTPException(415, "File is not decodable video/image media")
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    row = {"id": asset_id, "project_id": project_id,
           "filename": Path(file.filename or "upload").name[:200],
           "mime": file.content_type, "created": now()}
    with connect() as db:
        db.execute("INSERT INTO assets VALUES (:id,:project_id,:filename,:mime,:created)", row)
    return row


@app.get("/api/projects/{project_id}/assets/{asset_id}")
def get_asset(project_id: str, asset_id: str):
    with connect() as db:
        row = db.execute("SELECT * FROM assets WHERE id=? AND project_id=?",
                         (asset_id, project_id)).fetchone()
    if not row:
        raise HTTPException(404, "Asset not found")
    extension = {"video/mp4": ".mp4", "video/quicktime": ".mov", "video/webm": ".webm",
                 "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[row["mime"]]
    return FileResponse(ROOT / "assets" / project_id / (asset_id + extension),
                        media_type=row["mime"])


@app.post("/api/prompts/expand")
def expand_prompt(body: PromptIn):
    # Deterministic offline prompt composer; not falsely presented as an LLM response.
    base = re.sub(r"\s+", " ", body.idea).strip()
    return {"prompt": f"{base}. Genre: {body.genre}. Mood: {body.mood}. "
            "Professional cinematography, deliberate blocking, coherent subject continuity, "
            "controlled exposure, motivated lighting, photoreal textures, natural motion, "
            f"composition {body.aspect_ratio}, no logos or text overlays.",
            "engine": "deterministic-offline", "generated_video": False}


@app.post("/api/projects/{project_id}/render", status_code=201)
def render_project(project_id: str):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise HTTPException(503, "FFmpeg and ffprobe must be installed")
    with connect() as db:
        require_project(db, project_id)
        shots = [dict(x) for x in db.execute(
            "SELECT * FROM shots WHERE project_id=? ORDER BY position,id", (project_id,))]
        asset_rows = [dict(x) for x in db.execute(
            "SELECT * FROM assets WHERE project_id=?", (project_id,))]
    assets = {a["id"]: a for a in asset_rows}
    if not shots or any(not s["asset_id"] or s["asset_id"] not in assets for s in shots):
        raise HTTPException(400, "Every shot must have an uploaded video or image to render")
    render_id = uuid.uuid4().hex
    output_dir = ROOT / "renders" / project_id
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / f"{render_id}.mp4"
    with connect() as db:
        db.execute("INSERT INTO renders VALUES (?,?,?,?,?)",
                   (render_id, project_id, "processing", None, now()))
    try:
        with tempfile.TemporaryDirectory(dir=output_dir) as temp:
            segments = []
            for i, shot in enumerate(shots):
                asset = assets[shot["asset_id"]]
                ext = {"video/mp4": ".mp4", "video/quicktime": ".mov",
                       "video/webm": ".webm", "image/jpeg": ".jpg",
                       "image/png": ".png", "image/webp": ".webp"}[asset["mime"]]
                source = ROOT / "assets" / project_id / (asset["id"] + ext)
                segment = Path(temp) / f"shot-{i:04d}.mp4"
                cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
                if asset["mime"].startswith("image/"):
                    cmd += ["-loop", "1", "-framerate", "24"]
                cmd += ["-i", str(source), "-t", str(shot["duration"]),
                    "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,"
                    "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24",
                    "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-r", "24", str(segment)]
                subprocess.run(cmd, check=True, timeout=300, capture_output=True)
                segments.append(segment)
            listing = Path(temp) / "concat.txt"
            listing.write_text("".join(f"file '{p}'\n" for p in segments))
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                            "-f", "concat", "-safe", "0", "-i", str(listing),
                            "-c", "copy", "-movflags", "+faststart", str(result_path)],
                           check=True, timeout=300, capture_output=True)
        status, detail = "completed", None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        result_path.unlink(missing_ok=True)
        status, detail = "failed", str(exc)[:500]
    with connect() as db:
        db.execute("UPDATE renders SET status=?,detail=? WHERE id=?",
                   (status, detail, render_id))
    if status != "completed":
        raise HTTPException(500, f"Rendering failed: {detail}")
    return {"id": render_id, "status": status,
            "url": f"/api/projects/{project_id}/renders/{render_id}.mp4"}


@app.get("/api/projects/{project_id}/renders/{render_id}.mp4")
def download_render(project_id: str, render_id: str):
    with connect() as db:
        render = db.execute("SELECT 1 FROM renders WHERE id=? AND project_id=? AND status='completed'",
                            (render_id, project_id)).fetchone()
    if not render:
        raise HTTPException(404, "Render not found")
    return FileResponse(ROOT / "renders" / project_id / f"{render_id}.mp4",
                        media_type="video/mp4", filename=f"cinema-{render_id}.mp4")


from studio.models import router as model_router
app.include_router(model_router)

from fastapi.staticfiles import StaticFiles
app.mount("/", StaticFiles(directory=Path(__file__).parent / "web", html=True), name="studio")
