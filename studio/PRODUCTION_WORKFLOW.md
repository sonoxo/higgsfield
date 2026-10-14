# Cinema Studio — Production workflow phase

This changeset adds genuine browser-facing editorial functionality:

- Update shot camera, prompt and duration with persisted PATCH requests.
- Move shots left/right with server-side sequence validation.
- Export a structured JSON timeline containing ordered time ranges and source IDs.
- Queue one local FFmpeg render per project while allowing the HTTP request to return immediately.
- Poll job status and download the finished MP4.
- Configure an optional local Ollama or trusted OpenAI-compatible **text prompt** model.

Run: `git pull --ff-only && bash studio/start.sh`
Tests: `.venv/bin/python -m unittest discover -s studio/tests -v`

## Operational boundary

This is a single-host editorial workflow, not a studio-certified distributed media pipeline. The queue is in-process (lost on server restart), has one render thread and a 300-second per-FFmpeg command limit. It needs worker isolation, resumable jobs, persistent broker, media quotas, structured logs, access control, color management, audio mastering, versioning, and reliable orchestration before production deployment. Real video generation requires a separately licensed model/runtime or provider API and is not claimed to be wired.

All routes currently bind to localhost through the recommended startup script. Do not expose to the internet without access control. External provider endpoints are only enabled through operator-managed environment variables.
