#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON_BIN="${PYTHON_BIN:-python3}"
if [ ! -x .venv/bin/python ]; then "$PYTHON_BIN" -m venv .venv; fi
.venv/bin/python -m pip install -r studio/requirements.txt
.venv/bin/python -c 'import multipart, fastapi, pydantic, uvicorn; from studio.server import app; assert app is not None; print("Cinema API imports: OK")'
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
  echo 'NOTE: Install FFmpeg for rendering (macOS: brew install ffmpeg)' >&2
fi
exec .venv/bin/python -m uvicorn studio.server:app --host 127.0.0.1 --port "${PORT:-8000}"
