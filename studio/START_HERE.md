# Cinema Studio: local startup and model configuration

From the checked-out feature branch, use this command (also installs python-multipart in the **same** virtual environment as Uvicorn):

```bash
bash studio/start.sh
```

Open http://127.0.0.1:8000. Test health at http://127.0.0.1:8000/api/health.

### GPT-Doug local model through Ollama
Start your local Ollama server separately, download a model **you are licensed to run**, then launch Studio:

```bash
ollama pull llama3.2
CINEMA_OLLAMA_URL=http://127.0.0.1:11434 CINEMA_OLLAMA_MODEL=llama3.2 bash studio/start.sh
```

The **GPT-Doug LLM Enhance** button uses this configured model. It is for prompt generation, **not generated video**.

### Remote OpenAI-compatible endpoint
Set CINEMA_OPENAI_URL to the trusted provider's API base ending in /v1,
CINEMA_OPENAI_MODEL to a valid deployed model name, and CINEMA_OPENAI_API_KEY.
Never commit API keys. All provider URLs are read only from server environment variables.

### Run smoke tests
```bash
.venv/bin/python -m unittest discover -s studio/tests -v
```

Python 3.10+ recommended. ffmpeg/ffprobe required for rendering; on macOS install with `brew install ffmpeg`.

**Security:** The application binds to localhost intentionally. Do not expose on a public address without login, authorization, quotas, storage permissions, TLS, malware scanning, signed provider configuration, and an isolated asynchronous render worker. Connecting every model in existence is neither configured nor feasible automatically.
