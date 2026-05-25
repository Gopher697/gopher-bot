"""Tests for on-demand screen capture and sensor self-awareness."""
from __future__ import annotations

import sys
import time
import types
from unittest.mock import MagicMock, patch

from coordinators.tier_config import TIER_LOCAL


def test_screen_intent_detected_for_look_at_screen():
    from coordinators.sensory import _SCREEN_INTENT_RE

    assert _SCREEN_INTENT_RE.search("Can you look at my screen?") is not None


def test_screen_intent_detected_for_what_do_you_see():
    from coordinators.sensory import _SCREEN_INTENT_RE

    assert _SCREEN_INTENT_RE.search("What do you see on my screen?") is not None


def test_screen_intent_not_detected_for_normal_message():
    from coordinators.sensory import _SCREEN_INTENT_RE

    assert _SCREEN_INTENT_RE.search("What is the capital of France?") is None


def test_capture_screen_returns_none_when_mss_missing():
    from coordinators.sensory import _capture_screen

    with patch.dict(sys.modules, {"mss": None, "mss.tools": None}):
        result = _capture_screen()

    assert result is None


def test_capture_screen_returns_bytes_when_mss_available():
    from coordinators.sensory import _capture_screen

    fake_image = MagicMock()
    fake_image.rgb = b"rgb"
    fake_image.size = (100, 100)

    fake_sct = MagicMock()
    fake_sct.monitors = [{"left": 0, "top": 0, "width": 100, "height": 100}]
    fake_sct.grab.return_value = fake_image

    fake_context = MagicMock()
    fake_context.__enter__.return_value = fake_sct
    fake_context.__exit__.return_value = False

    fake_mss = types.ModuleType("mss")
    fake_tools = types.ModuleType("mss.tools")
    fake_mss.mss = MagicMock(return_value=fake_context)
    fake_mss.tools = fake_tools
    fake_tools.to_png = MagicMock(return_value=b"fakepng")

    with patch.dict(sys.modules, {"mss": fake_mss, "mss.tools": fake_tools}):
        result = _capture_screen()

    assert result == b"fakepng"


def test_sensory_on_demand_capture_local_tier():
    from coordinators.sensory import Sensory

    packet = {
        "message": "What do you see on my screen?",
        "tier": TIER_LOCAL,
    }
    tier_config = {
        "base_url": "http://localhost:1234/v1",
        "sensory_model": "qwen3.5",
    }
    with (
        patch("coordinators.sensory._capture_screen", return_value=b"fakepng"),
        patch("coordinators.sensory.get_tier_config", return_value=tier_config),
        patch.object(
            Sensory,
            "classify",
            return_value={"intent": "screen", "keywords": ["screen"]},
        ),
    ):
        result = Sensory().process(packet)

    assert "raw_images_for_reason" in result
    assert result["raw_images_for_reason"][0]["media_type"] == "image/png"
    assert result["visual_percept"]["scene_type"] == "on_demand_capture"
    assert result["visual_percept"]["description"] == ""


def test_sensory_no_capture_for_normal_message():
    from coordinators.sensory import Sensory

    packet = {
        "message": "What is the capital of France?",
        "tier": TIER_LOCAL,
    }
    with (
        patch("coordinators.sensory._capture_screen", return_value=b"fakepng") as capture,
        patch("coordinators.sensory.VisionSensor.get_latest", return_value=None),
        patch.object(
            Sensory,
            "classify",
            return_value={"intent": "question", "keywords": ["capital"]},
        ),
    ):
        Sensory().process(packet)

    capture.assert_not_called()


def test_operational_context_includes_screen_sensor():
    from coordinators.orientation import _operational_context

    with (
        patch("coordinators.orientation._sensor_available", return_value=True),
        patch("sensors.vision_sensor.VisionSensor.get_latest", return_value=None),
    ):
        result = _operational_context({}, time.time())

    assert "screen-capture" in result


def test_operational_context_no_sensor_when_mss_missing():
    from coordinators.orientation import _operational_context

    with (
        patch("coordinators.orientation._sensor_available", return_value=False),
        patch("sensors.vision_sensor.VisionSensor.get_latest", return_value=None),
    ):
        result = _operational_context({}, time.time())

    assert "Sensors" not in result
