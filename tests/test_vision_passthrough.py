"""Tests for passing user image bytes through to local VLM Reason calls."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from coordinators.reason import Reason, _call_local_reasoner
from coordinators.sensory import Sensory
from coordinators.tier_config import TIER_LOCAL


def _local_classifier_response():
    return MagicMock(
        choices=[
            MagicMock(message=MagicMock(content='{"intent": "share", "keywords": ["image"]}'))
        ]
    )


def _anthropic_classifier_response():
    response = MagicMock()
    response.choices = None
    response.content = [MagicMock(text='{"intent": "share", "keywords": ["image"]}')]
    return response


def test_sensory_local_tier_sets_raw_images():
    packet = {
        "message": "what is in this image?",
        "tier": TIER_LOCAL,
        "image_attachments": [{"filename": "test.png", "data": b"\x89PNG..."}],
    }
    tier_config = {
        "base_url": "http://localhost:1234/v1",
        "sensory_model": "qwen3.5",
    }
    with (
        patch("coordinators.sensory.get_tier_config", return_value=tier_config),
        patch("coordinators.sensory._call_local_classifier", return_value=_local_classifier_response()),
    ):
        result = Sensory().process(packet)

    assert result["raw_images_for_reason"]
    assert result["raw_images_for_reason"][0]["media_type"] == "image/png"
    assert result["raw_images_for_reason"][0]["data_b64"]
    assert result.get("visual_percept", {}).get("description") == ""
    assert "image_attachments" not in result


def test_sensory_cloud_tier_uses_describe_image():
    packet = {
        "message": "what is in this image?",
        "tier": 2,
        "image_attachments": [{"filename": "test.png", "data": b"\x89PNG..."}],
    }
    tier_config = {
        "base_url": None,
        "sensory_model": "claude-haiku-4-5-20251001",
    }
    with (
        patch("coordinators.sensory.get_tier_config", return_value=tier_config),
        patch("coordinators.sensory._describe_image", return_value="A palm tree pixel art image."),
        patch("coordinators.sensory._call_anthropic_classifier", return_value=_anthropic_classifier_response()),
    ):
        result = Sensory().process(packet)

    assert "raw_images_for_reason" not in result
    assert "[test.png]: A palm tree pixel art image." in result["visual_percept"]["description"]


def test_sensory_local_tier_no_images_no_key():
    packet = {"message": "hello", "tier": TIER_LOCAL}
    with patch("coordinators.sensory._call_local_classifier", return_value=_local_classifier_response()):
        result = Sensory().process(packet)
    assert "raw_images_for_reason" not in result


def test_call_local_reasoner_with_images_builds_multimodal_content():
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="ok"))]
    )
    raw_images = [{"media_type": "image/png", "data_b64": "abc123"}]

    with patch("coordinators.reason.OpenAI", return_value=fake_client):
        _call_local_reasoner(
            "describe it",
            "system",
            {"base_url": "http://localhost:1234/v1", "reason_model": "qwen3.5"},
            raw_images=raw_images,
        )

    messages = fake_client.chat.completions.create.call_args.kwargs["messages"]
    user_content = messages[1]["content"]
    assert isinstance(user_content, list)
    image_block = next(block for block in user_content if block["type"] == "image_url")
    assert image_block["image_url"]["url"].startswith("data:image/png;base64,")
    text_block = next(block for block in user_content if block["type"] == "text")
    assert text_block["text"] == "describe it"


def test_call_local_reasoner_without_images_sends_string():
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="ok"))]
    )

    with patch("coordinators.reason.OpenAI", return_value=fake_client):
        _call_local_reasoner(
            "describe it",
            "system",
            {"base_url": "http://localhost:1234/v1", "reason_model": "qwen3.5"},
            raw_images=[],
        )

    messages = fake_client.chat.completions.create.call_args.kwargs["messages"]
    assert messages[1]["content"] == "describe it"


def test_generate_response_no_visual_text_when_raw_images_present():
    reason = Reason()
    captured = {}

    def fake_local(message, system_prompt, tier_config, lm_studio_api_key=None, raw_images=None):
        captured["system_prompt"] = system_prompt
        return MagicMock(choices=[MagicMock(message=MagicMock(content="ok"))])

    with patch("coordinators.reason._call_local_reasoner", fake_local):
        reason.generate_response(
            "what is this?",
            "",
            TIER_LOCAL,
            "some text",
            raw_images=[{"media_type": "image/png", "data_b64": "abc123"}],
        )

    assert "Visual context" not in captured["system_prompt"]


def test_generate_response_visual_text_when_no_raw_images():
    reason = Reason()
    captured = {}

    def fake_local(message, system_prompt, tier_config, lm_studio_api_key=None, raw_images=None):
        captured["system_prompt"] = system_prompt
        return MagicMock(choices=[MagicMock(message=MagicMock(content="ok"))])

    with patch("coordinators.reason._call_local_reasoner", fake_local):
        reason.generate_response(
            "what is this?",
            "",
            TIER_LOCAL,
            "A palm tree.",
            raw_images=[],
        )

    assert "Visual context" in captured["system_prompt"]
