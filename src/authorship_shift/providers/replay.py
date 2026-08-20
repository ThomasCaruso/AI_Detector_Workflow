from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from ..engine_v2 import GenerationControls


class ReplayGenerator:
    """Feeds pre-generated candidate texts into Engine v2.

    This is useful when candidates were created manually in ChatGPT, Codex, or
    another model surface and should be evaluated without an API call. Files are
    consumed in deterministic order.
    """

    def __init__(self, responses: Iterable[str], *, identity: str = "replay"):
        self._responses = [str(response).strip() for response in responses]
        if not self._responses:
            raise ValueError("ReplayGenerator requires at least one response")
        if any(not response for response in self._responses):
            raise ValueError("ReplayGenerator responses must not be empty")
        self._cursor = 0
        self._identity = identity
        self.calls: list[dict] = []

    @property
    def identity(self) -> str:
        return self._identity

    @classmethod
    def from_directory(
        cls,
        directory: str | Path,
        *,
        pattern: str = "*.txt",
        identity: str = "replay-files",
    ) -> "ReplayGenerator":
        root = Path(directory)
        paths = sorted(path for path in root.glob(pattern) if path.is_file())
        if not paths:
            raise ValueError(f"no candidate files matched {pattern!r} in {root}")
        return cls(
            [path.read_text(encoding="utf-8") for path in paths],
            identity=identity,
        )

    @property
    def remaining(self) -> int:
        return len(self._responses) - self._cursor

    def generate(
        self,
        *,
        source: str,
        content_atoms: Sequence[str],
        directive: str,
        controls: GenerationControls,
    ) -> str:
        if self._cursor >= len(self._responses):
            raise RuntimeError("ReplayGenerator has no responses remaining")

        response = self._responses[self._cursor]
        self._cursor += 1
        self.calls.append(
            {
                "source": source,
                "content_atoms": list(content_atoms),
                "directive": directive,
                "controls": controls.to_dict(),
            }
        )
        return response
