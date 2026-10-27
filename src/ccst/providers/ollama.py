"""Local Ollama provider, using structured outputs (the `format` parameter)."""

import time

import httpx

from ..config import settings
from .base import Completion, ProviderError, TruncatedOutput


class OllamaProvider:
    name = "ollama"

    def __init__(self, url: str = settings.ollama_url, model: str = settings.ollama_model):
        self.url = url.rstrip("/")
        self.model = model

    async def complete_json(self, system: str, user: str, schema: dict, max_tokens: int) -> Completion:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "format": schema,
            "stream": False,
            "think": False,  # reasoning traces cost minutes on CPU; structured output doesn't need them
            "options": {"temperature": 0.7, "num_ctx": settings.ollama_num_ctx, "num_predict": max_tokens},
        }
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=settings.ollama_timeout_s) as client:
                r = await client.post(f"{self.url}/api/chat", json=body)
        except httpx.HTTPError as e:
            raise ProviderError(f"cannot reach Ollama at {self.url}: {e!r}") from e
        if r.status_code != 200:
            raise ProviderError(f"Ollama returned HTTP {r.status_code}: {r.text[:300]}")
        data = r.json()
        stop = data.get("done_reason", "")
        if stop == "length":
            raise TruncatedOutput(f"output hit num_predict={max_tokens}; batch discarded")
        return Completion(
            text=data.get("message", {}).get("content", ""),
            model=data.get("model", self.model),
            stop_reason=stop,
            input_tokens=data.get("prompt_eval_count"),
            output_tokens=data.get("eval_count"),
            seconds=round(time.monotonic() - started, 1),
        )

    async def health(self) -> dict:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{self.url}/api/tags")
            names = [m.get("name") for m in r.json().get("models", [])]
            return {"reachable": True, "model_present": self.model in names}
        except (httpx.HTTPError, ValueError):
            return {"reachable": False, "model_present": False}
