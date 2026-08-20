from __future__ import annotations

import json
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from .base import Provider


class OllamaProvider(Provider):
    def __init__(self, model: str = "gemma3", base_url: str = "http://localhost:11434", temperature: float = 0.8):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature

    @property
    def identity(self) -> str:
        return f"ollama:{self.model}@t{self.temperature:g}"

    def chat(self, prompt: str, *, system: str | None = None, json_mode: bool = False) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": self.temperature},
        }
        if json_mode:
            payload["format"] = "json"
        req = Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=600) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (URLError, HTTPError) as exc:
            raise RuntimeError(f"Ollama request failed: {exc}") from exc
        return data["message"]["content"]
