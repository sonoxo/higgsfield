# GPT-Doug Cinema Studio (original video production application)

A standalone FastAPI + browser frontend integrated as a separate package alongside the existing Higgsfield GPU-training code. This is **not** the commercial Higgsfield application or a copy of its proprietary frontend.

## Start

Install FFmpeg and ffprobe, then from repository root:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r studio/requirements.txt
uvicorn studio.server:app --host 127.0.0.1 --port 8000
```

Visit http://127.0.0.1:8000. Create a production, upload media, create storyboard shots with the asset selected, and click Render Film. You get an actual H.264 1080p MP4 assembled by FFmpeg.

## Current implementation
- Persistent SQLite projects, shot list and assets
- Original responsive dark studio interface
- Deterministic prompt composer (not an LLM)
- Server-side media validation with ffprobe; size-limited uploads
- Shot assembly into 1080p, 24 fps H.264 MP4
- Downloadable render jobs and health endpoint

## Production limitations
- This version does **not** produce generative AI video; it assembles user-provided assets.
- No GPT-Doug LLM inference, Higgsfield commercial API, payments, model weights, collaborative auth, sound mixing, video extension, or cloud GPU workers are wired.
- FFmpeg jobs are synchronous and require a worker queue, concurrency limits, retention controls, resource quotas, and retry strategies before multi-tenant production deployment.
- Authentication and permission checks must be added **before exposing the server publicly**.
- Local SQLite and disk files must become managed DB and object storage for clustered use.
- Studio-grade delivery requires color-managed pipelines, sound, metadata, master formats, editorial interchange, QC, and legal clearance.

## API
`GET /api/health`; `GET,POST /api/projects`; `GET /api/projects/{id}`; `POST /api/projects/{id}/shots`; `DELETE /api/projects/{id}/shots/{shot_id}`; `POST /api/projects/{id}/assets`; `GET /api/projects/{id}/assets/{asset_id}`; `POST /api/prompts/expand`; `POST /api/projects/{id}/render`; `GET /api/projects/{id}/renders/{render_id}.mp4`.

Dependency installation is deliberately opt-in; existing Higgsfield training dependencies remain unchanged.
