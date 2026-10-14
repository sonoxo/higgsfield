"""Opt-in model routing; endpoints are configured by the operator, not user input."""
import json
import os
import urllib.error
import urllib.request

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/models", tags=["models"])
AVAILABLE = ("ollama", "openai-compatible")


class Completion(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    provider: str = "ollama"
    model: str = Field(default="", max_length=160)


@router.get("")
def providers():
    return {"providers": [
        {"name": "ollama", "enabled": bool(os.getenv("CINEMA_OLLAMA_URL")),
         "model": os.getenv("CINEMA_OLLAMA_MODEL", "llama3.2")},
        {"name": "openai-compatible", "enabled": bool(os.getenv("CINEMA_OPENAI_URL")),
         "model": os.getenv("CINEMA_OPENAI_MODEL", "")}
    ], "mode": "operator-configured", "automatic_all_model_access": False}


def request_json(url: str, payload: dict, key: str = ""):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            if response.status != 200:
                raise HTTPException(502, "Model service returned an error")
            return json.loads(response.read(2 * 1024 * 1024).decode())
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise HTTPException(502, "Configured model endpoint unavailable") from exc


@router.post("/complete")
def complete(body: Completion):
    if body.provider not in AVAILABLE:
        raise HTTPException(400, "Unsupported provider")
    system = ("You are GPT-Doug Cinema Studio's film prompt assistant. Convert the "
              "request into a concise shot specification with subject, environment, "
              "camera, lighting, motion, mood and continuity; no claims of generated video.")
    if body.provider == "ollama":
        root = os.getenv("CINEMA_OLLAMA_URL", "").rstrip("/")
        if not root:
            raise HTTPException(503, "Ollama not configured")
        model = body.model or os.getenv("CINEMA_OLLAMA_MODEL", "llama3.2")
        data = request_json(root + "/api/chat", {"model": model, "stream": False,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": body.prompt}]})
        answer = data.get("message", {}).get("content", "")
    else:
        root = os.getenv("CINEMA_OPENAI_URL", "").rstrip("/")
        key = os.getenv("CINEMA_OPENAI_API_KEY", "")
        if not root or not key:
            raise HTTPException(503, "OpenAI-compatible provider not configured")
        model = body.model or os.getenv("CINEMA_OPENAI_MODEL", "")
        if not model:
            raise HTTPException(400, "Set CINEMA_OPENAI_MODEL or provide a model")
        data = request_json(root + "/chat/completions", {"model": model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": body.prompt}]}, key)
        try:
            answer = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise HTTPException(502, "Invalid model response") from exc
    if not answer:
        raise HTTPException(502, "Model returned no text")
    return {"prompt": answer, "provider": body.provider, "model": model,
            "generated_video": False}
