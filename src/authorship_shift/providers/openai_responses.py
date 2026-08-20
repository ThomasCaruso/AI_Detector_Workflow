from __future__ import annotations

import json
import os
from typing import Callable, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..engine_v2 import GenerationControls


Transport = Callable[[Request, float], bytes]


def _default_transport(request: Request, timeout: float) -> bytes:
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed HTTPS API endpoint by default
        return response.read()


def _extract_output_text(payload: dict) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    chunks: list[str] = []
    for item in payload.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []) or []:
            if not isinstance(content, dict):
                continue
            if content.get("type") == "output_text":
                text = content.get("text")
                if isinstance(text, str) and text:
                    chunks.append(text)
    return "".join(chunks).strip()


class OpenAIResponsesGenerator:
    """Engine v2 generator backed by the OpenAI Responses API.

    The provider intentionally has no dependency on the OpenAI Python package;
    it uses the HTTPS Responses endpoint directly. Sampling parameters are
    omitted by default because support is model-dependent. Set
    ``allow_sampling_controls=True`` only for a model/API combination that you
    have verified accepts ``temperature`` and ``top_p``.

    ``seed`` is recorded by Engine v2 for experiment provenance but is not sent
    to the Responses API by this provider.
    """

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        endpoint: str = "https://api.openai.com/v1/responses",
        timeout: float = 90.0,
        allow_sampling_controls: bool = False,
        transport: Transport | None = None,
    ) -> None:
        if not model.strip():
            raise ValueError("model must not be empty")
        self.model = model.strip()
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.endpoint = endpoint
        self.timeout = timeout
        self.allow_sampling_controls = allow_sampling_controls
        self._transport = transport or _default_transport

    @property
    def identity(self) -> str:
        return f"openai-responses:{self.model}"

    def _prompt(
        self,
        *,
        source: str,
        content_atoms: Sequence[str],
        directive: str,
    ) -> str:
        atoms = "\n".join(f"- {atom}" for atom in content_atoms)
        return (
            "Write one independent candidate for the supplied writing task.\n\n"
            "PROFILE DIRECTIVE\n"
            f"{directive.strip() or 'Use clear, specific prose that fits the task.'}\n\n"
            "CONTENT ATOMS\n"
            f"{atoms}\n\n"
            "SOURCE / TASK\n"
            f"{source.strip()}\n\n"
            "REQUIREMENTS\n"
            "- Preserve the supplied facts, relationships, qualifications, and level of certainty.\n"
            "- Do not invent evidence, experience, citations, or factual details.\n"
            "- Follow any requested length, format, or audience constraints in the source/task.\n"
            "- Use the profile directive to choose a genuinely independent organization and sentence path.\n"
            "- Return only the finished prose."
        )

    def _payload(
        self,
        *,
        source: str,
        content_atoms: Sequence[str],
        directive: str,
        controls: GenerationControls,
    ) -> dict:
        payload: dict = {
            "model": self.model,
            "input": self._prompt(
                source=source,
                content_atoms=content_atoms,
                directive=directive,
            ),
        }
        if controls.max_tokens is not None:
            payload["max_output_tokens"] = int(controls.max_tokens)
        if self.allow_sampling_controls:
            if controls.temperature is not None:
                payload["temperature"] = float(controls.temperature)
            if controls.top_p is not None:
                payload["top_p"] = float(controls.top_p)
        return payload

    def generate(
        self,
        *,
        source: str,
        content_atoms: Sequence[str],
        directive: str,
        controls: GenerationControls,
    ) -> str:
        if not self.api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Use the manual/replay workflow or provide an API key explicitly."
            )

        payload = self._payload(
            source=source,
            content_atoms=content_atoms,
            directive=directive,
            controls=controls,
        )
        request = Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            raw = self._transport(request, self.timeout)
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"OpenAI Responses API returned HTTP {exc.code}: {body[:1000]}"
            ) from exc
        except URLError as exc:
            raise RuntimeError(f"OpenAI Responses API request failed: {exc}") from exc

        try:
            response = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("OpenAI Responses API returned invalid JSON") from exc

        text = _extract_output_text(response)
        if not text:
            raise RuntimeError(
                "OpenAI Responses API response contained no output_text content"
            )
        return text
