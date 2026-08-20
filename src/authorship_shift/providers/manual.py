from __future__ import annotations
from pathlib import Path
import time
from .base import Provider


class ManualProvider(Provider):
    """Writes prompts to an outbox instead of spending API credits."""
    def __init__(self, outbox: str | Path):
        self.outbox = Path(outbox)
        self.outbox.mkdir(parents=True, exist_ok=True)

    @property
    def identity(self) -> str:
        return "manual"

    def chat(self, prompt: str, *, system: str | None = None, json_mode: bool = False) -> str:
        stamp = int(time.time() * 1000)
        path = self.outbox / f"prompt_{stamp}.md"
        body = ""
        if system:
            body += f"# System\n\n{system}\n\n"
        body += f"# Task\n\n{prompt}\n"
        if json_mode:
            body += "\n# Output requirement\n\nReturn valid JSON only.\n"
        path.write_text(body, encoding="utf-8")
        raise RuntimeError(f"Manual mode: prompt written to {path}. Run it in your chosen model, then ingest the result.")
