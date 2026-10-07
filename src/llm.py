"""Thin Ollama client. Uses native /api/chat because it supports format=json and num_ctx."""
import os

import httpx


def _base_url() -> str:
    url = os.getenv(
        "LLM_BASE_URL",
        "http://localhost:11434",
    ).rstrip("/")
    return url[:-3] if url.endswith("/v1") else url


def chat(messages: list[dict], json_mode: bool = True, timeout: float = 180.0) -> str:
    payload: dict = {
        "model": os.getenv("LLM_MODEL", "qwen2.5-coder:7b"),
        "messages": messages,
        "stream": False,
        # temperature 0: the verifier needs reproducible behavior, not creativity
        "options": {
            "num_ctx": int(os.getenv("NUM_CTX", "8192")),
            "temperature": 0,
        },
    }

    if json_mode:
        payload["format"] = "json"

    last_err: Exception | None = None

    for _ in range(2):
        try:
            r = httpx.post(
                f"{_base_url()}/api/chat",
                json=payload,
                timeout=timeout,
            )
            r.raise_for_status()
            return r.json()["message"]["content"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            last_err = exc

    raise RuntimeError(
        f"LLM call failed after retry ({last_err}). "
        "Is Ollama running and the model pulled?"
    )
