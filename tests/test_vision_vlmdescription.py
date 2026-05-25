"""Tests for VLM semantic scene description in VisionSensor."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import sensors.vision_sensor as vs_mod
from coordinators.percepts import VisualPercept
from sensors.vision_sensor import (
    VISION_VLM_BASE_URL,
    VISION_VLM_MODEL,
    VISION_VLM_TIMEOUT,
    VisionSensor,
)


# -- Constants ----------------------------------------------------------------

def test_vlm_constants_exist_and_are_correct_types():
    assert isinstance(VISION_VLM_MODEL, str)
    assert isinstance(VISION_VLM_BASE_URL, str)
    assert isinstance(VISION_VLM_TIMEOUT, int)
    assert VISION_VLM_TIMEOUT > 0


def test_vlm_model_defaults_to_empty_string():
    """Default must be empty so VLM path is opt-in."""
    assert VISION_VLM_MODEL == ""


# -- _grab_png_bytes -----------------------------------------------------------

def test_grab_png_bytes_returns_none_without_sct():
    sensor = VisionSensor()
    sensor._sct = None
    assert sensor._grab_png_bytes() is None


def test_grab_png_bytes_returns_none_on_grab_failure():
    sensor = VisionSensor()
    sensor._sct = MagicMock()
    sensor._sct.grab.side_effect = RuntimeError("mss error")
    assert sensor._grab_png_bytes() is None


# -- _describe_with_vlm --------------------------------------------------------

def test_describe_with_vlm_returns_empty_when_model_not_configured():
    """VISION_VLM_MODEL == '' means the VLM path is entirely skipped."""
    original = vs_mod.VISION_VLM_MODEL
    vs_mod.VISION_VLM_MODEL = ""
    try:
        sensor = VisionSensor()
        result = sensor._describe_with_vlm(b"fake_png_bytes")
        assert result == ""
    finally:
        vs_mod.VISION_VLM_MODEL = original


def test_describe_with_vlm_returns_empty_for_empty_bytes():
    original = vs_mod.VISION_VLM_MODEL
    vs_mod.VISION_VLM_MODEL = "qwen2-vl-test"
    try:
        sensor = VisionSensor()
        result = sensor._describe_with_vlm(b"")
        assert result == ""
    finally:
        vs_mod.VISION_VLM_MODEL = original


def test_describe_with_vlm_returns_empty_on_api_failure():
    """Any exception from LM Studio returns '' -- no hang, no crash."""
    original = vs_mod.VISION_VLM_MODEL
    vs_mod.VISION_VLM_MODEL = "qwen2-vl-test"
    try:
        sensor = VisionSensor()
        with patch.object(vs_mod, "OpenAI", side_effect=Exception("connection refused")):
            result = sensor._describe_with_vlm(b"fake_png_bytes")
        assert result == ""
    finally:
        vs_mod.VISION_VLM_MODEL = original


def test_describe_with_vlm_returns_description_on_success():
    original = vs_mod.VISION_VLM_MODEL
    vs_mod.VISION_VLM_MODEL = "qwen2-vl-test"
    try:
        sensor = VisionSensor()
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="User is playing Stellaris."))]
        )
        with patch.object(vs_mod, "OpenAI", return_value=fake_client):
            result = sensor._describe_with_vlm(b"fake_png_bytes")
        assert result == "User is playing Stellaris."
    finally:
        vs_mod.VISION_VLM_MODEL = original


def test_describe_with_vlm_passes_correct_base64_and_prompt():
    """VLM call uses base64-encoded PNG and the expected prompt text."""
    import base64

    original = vs_mod.VISION_VLM_MODEL
    vs_mod.VISION_VLM_MODEL = "qwen2-vl-test"
    try:
        sensor = VisionSensor()
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="ok"))]
        )
        test_bytes = b"png_content"
        with patch.object(vs_mod, "OpenAI", return_value=fake_client):
            sensor._describe_with_vlm(test_bytes)

        call_kwargs = fake_client.chat.completions.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs.args[0]
        content = messages[0]["content"]

        image_block = next(b for b in content if b.get("type") == "image_url")
        expected_b64 = base64.standard_b64encode(test_bytes).decode("utf-8")
        assert expected_b64 in image_block["image_url"]["url"]

        text_block = next(b for b in content if b.get("type") == "text")
        assert "describe" in text_block["text"].lower()
    finally:
        vs_mod.VISION_VLM_MODEL = original


def test_describe_with_vlm_uses_configured_timeout():
    original = vs_mod.VISION_VLM_MODEL
    vs_mod.VISION_VLM_MODEL = "qwen2-vl-test"
    try:
        sensor = VisionSensor()
        created_clients = []

        class FakeOpenAI:
            def __init__(self, **kwargs):
                created_clients.append(kwargs)
                self.chat = MagicMock()
                self.chat.completions.create.return_value = MagicMock(
                    choices=[MagicMock(message=MagicMock(content="ok"))]
                )

        with patch.object(vs_mod, "OpenAI", FakeOpenAI):
            sensor._describe_with_vlm(b"fake_png")

        assert created_clients[0].get("timeout") == vs_mod.VISION_VLM_TIMEOUT
    finally:
        vs_mod.VISION_VLM_MODEL = original


# -- _maybe_store_observation with VLM enrichment -----------------------------

def test_maybe_store_observation_enriches_description_when_vlm_succeeds():
    """Stored observation includes mechanical + Scene: VLM prose."""
    original = vs_mod.VISION_VLM_MODEL
    vs_mod.VISION_VLM_MODEL = "qwen2-vl-test"
    try:
        sensor = VisionSensor()
        sensor._memory = MagicMock()
        sensor._memory.store_visual_observation.return_value = True
        sensor._last_stored_ts = 0.0

        percept = VisualPercept(
            timestamp=1000.0,
            description='Window: "Stellaris"',
            scene_type="desktop",
        )

        sensor._grab_png_bytes = MagicMock(return_value=b"fake_png")
        sensor._describe_with_vlm = MagicMock(
            return_value="User is in a fleet battle, resources critical."
        )

        sensor._maybe_store_observation(percept, "Stellaris")

        stored_arg = sensor._memory.store_visual_observation.call_args[0][0]
        assert 'Window: "Stellaris"' in stored_arg.description
        assert "Scene: User is in a fleet battle" in stored_arg.description
    finally:
        vs_mod.VISION_VLM_MODEL = original


def test_maybe_store_observation_stores_unchanged_when_vlm_returns_empty():
    """If VLM returns '', mechanical description is stored as-is."""
    original = vs_mod.VISION_VLM_MODEL
    vs_mod.VISION_VLM_MODEL = "qwen2-vl-test"
    try:
        sensor = VisionSensor()
        sensor._memory = MagicMock()
        sensor._memory.store_visual_observation.return_value = True
        sensor._last_stored_ts = 0.0

        percept = VisualPercept(
            timestamp=1000.0,
            description='Window: "Chrome"',
            scene_type="desktop",
        )

        sensor._grab_png_bytes = MagicMock(return_value=b"fake_png")
        sensor._describe_with_vlm = MagicMock(return_value="")

        sensor._maybe_store_observation(percept, "Chrome")

        stored_arg = sensor._memory.store_visual_observation.call_args[0][0]
        assert stored_arg.description == 'Window: "Chrome"'
        assert "Scene:" not in stored_arg.description
    finally:
        vs_mod.VISION_VLM_MODEL = original


def test_maybe_store_observation_does_not_mutate_live_percept():
    """_latest_percept must keep the mechanical description."""
    original = vs_mod.VISION_VLM_MODEL
    vs_mod.VISION_VLM_MODEL = "qwen2-vl-test"
    try:
        sensor = VisionSensor()
        sensor._memory = MagicMock()
        sensor._memory.store_visual_observation.return_value = True
        sensor._last_stored_ts = 0.0

        original_desc = 'Window: "Notepad"'
        percept = VisualPercept(
            timestamp=1000.0,
            description=original_desc,
            scene_type="desktop",
        )

        sensor._grab_png_bytes = MagicMock(return_value=b"fake_png")
        sensor._describe_with_vlm = MagicMock(return_value="User is editing a text file.")

        sensor._maybe_store_observation(percept, "Notepad")

        assert percept.description == original_desc
    finally:
        vs_mod.VISION_VLM_MODEL = original


def test_maybe_store_observation_skips_vlm_when_model_not_configured():
    """When VISION_VLM_MODEL is empty, _grab_png_bytes is never called."""
    original = vs_mod.VISION_VLM_MODEL
    vs_mod.VISION_VLM_MODEL = ""
    try:
        sensor = VisionSensor()
        sensor._memory = MagicMock()
        sensor._memory.store_visual_observation.return_value = True
        sensor._last_stored_ts = 0.0

        percept = VisualPercept(
            timestamp=1000.0,
            description='Window: "Discord"',
            scene_type="desktop",
        )

        sensor._grab_png_bytes = MagicMock()

        sensor._maybe_store_observation(percept, "Discord")

        sensor._grab_png_bytes.assert_not_called()
    finally:
        vs_mod.VISION_VLM_MODEL = original
