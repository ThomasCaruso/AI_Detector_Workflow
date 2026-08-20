import json

import pytest

from authorship_shift.engine_v2 import GenerationControls
from authorship_shift.providers.openai_responses import OpenAIResponsesGenerator


def test_openai_responses_provider_builds_request_and_extracts_text():
    captured = {}

    def transport(request, timeout):
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return json.dumps(
            {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": "Candidate prose."}
                        ],
                    }
                ]
            }
        ).encode("utf-8")

    generator = OpenAIResponsesGenerator(
        "test-model",
        api_key="test-key",
        transport=transport,
    )
    text = generator.generate(
        source="Northstar grew 27% in 2025.",
        content_atoms=["preserve 27%", "preserve 2025"],
        directive="Begin with the mechanism.",
        controls=GenerationControls(
            temperature=0.9,
            top_p=0.8,
            seed=42,
            max_tokens=600,
        ),
    )

    assert text == "Candidate prose."
    assert captured["payload"]["model"] == "test-model"
    assert captured["payload"]["max_output_tokens"] == 600
    assert "temperature" not in captured["payload"]
    assert "top_p" not in captured["payload"]
    assert "seed" not in captured["payload"]
    assert "Northstar grew 27% in 2025." in captured["payload"]["input"]
    assert "Begin with the mechanism." in captured["payload"]["input"]


def test_sampling_controls_are_opt_in_and_seed_is_not_sent():
    captured = {}

    def transport(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return json.dumps({"output_text": "Alternative."}).encode("utf-8")

    generator = OpenAIResponsesGenerator(
        "sampling-model",
        api_key="test-key",
        allow_sampling_controls=True,
        transport=transport,
    )
    text = generator.generate(
        source="Source.",
        content_atoms=["fact"],
        directive="Directive.",
        controls=GenerationControls(temperature=0.7, top_p=0.91, seed=99),
    )

    assert text == "Alternative."
    assert captured["payload"]["temperature"] == 0.7
    assert captured["payload"]["top_p"] == 0.91
    assert "seed" not in captured["payload"]


def test_provider_requires_api_key_before_network_call(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    generator = OpenAIResponsesGenerator("test-model", api_key=None)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        generator.generate(
            source="Source.",
            content_atoms=["fact"],
            directive="Directive.",
            controls=GenerationControls(),
        )


def test_provider_rejects_empty_model():
    with pytest.raises(ValueError, match="model"):
        OpenAIResponsesGenerator("   ", api_key="test-key")
