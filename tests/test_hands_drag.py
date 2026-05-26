"""Tests for OmniParser screen location and Hands drag primitives."""
from __future__ import annotations

import json
import sys
import types
from unittest.mock import MagicMock, patch


def _install_fake_mss(png_bytes: bytes = b"fakepng") -> tuple[types.ModuleType, types.ModuleType]:
    fake_image = MagicMock()
    fake_image.rgb = b"rgb"
    fake_image.size = (100, 100)

    fake_sct = MagicMock()
    fake_sct.monitors = [
        {"left": 0, "top": 0, "width": 100, "height": 100},
        {"left": 0, "top": 0, "width": 50, "height": 50},
    ]
    fake_sct.grab.return_value = fake_image

    fake_context = MagicMock()
    fake_context.__enter__.return_value = fake_sct
    fake_context.__exit__.return_value = False

    fake_mss = types.ModuleType("mss")
    fake_tools = types.ModuleType("mss.tools")
    fake_mss.mss = MagicMock(return_value=fake_context)
    fake_mss.tools = fake_tools
    fake_tools.to_png = MagicMock(return_value=png_bytes)
    return fake_mss, fake_tools


def test_locate_on_screen_omniparser_unavailable():
    from coordinators.hands import _handle_locate_on_screen

    fake_mss, fake_tools = _install_fake_mss()
    with (
        patch.dict(sys.modules, {"mss": fake_mss, "mss.tools": fake_tools}),
        patch("sensors.omni_parser.locate_element", return_value=None),
    ):
        result = _handle_locate_on_screen({"description": "submit button"})

    data = json.loads(result)
    assert data["found"] is False


def test_locate_on_screen_element_found():
    from coordinators.hands import _handle_locate_on_screen

    fake_mss, fake_tools = _install_fake_mss()
    located = {"label": "OK", "bbox": [100, 200, 150, 220], "center": [125, 210]}
    with (
        patch.dict(sys.modules, {"mss": fake_mss, "mss.tools": fake_tools}),
        patch("sensors.omni_parser.locate_element", return_value=located),
    ):
        result = _handle_locate_on_screen({"description": "ok button"})

    data = json.loads(result)
    assert data["found"] is True
    assert data["label"] == "OK"
    assert data["center"] == [125, 210]


def test_drag_to_pyautogui_present():
    import coordinators.hands as hands_mod

    fake_pyautogui = MagicMock()
    with patch.object(hands_mod, "pyautogui", fake_pyautogui):
        result = hands_mod._handle_drag_to({"x1": 10, "y1": 20, "x2": 30, "y2": 40})

    fake_pyautogui.moveTo.assert_called_once_with(10, 20, duration=0.1)
    fake_pyautogui.dragTo.assert_called_once_with(30, 40, duration=0.4, button="left")
    assert result


def test_drag_to_pyautogui_absent():
    import coordinators.hands as hands_mod

    with patch.object(hands_mod, "pyautogui", None):
        result = hands_mod._handle_drag_to({"x1": 10, "y1": 20, "x2": 30, "y2": 40})

    assert "Error" in result


def test_drag_element_source_not_found():
    import coordinators.hands as hands_mod

    fake_mss, fake_tools = _install_fake_mss()
    with (
        patch.dict(sys.modules, {"mss": fake_mss, "mss.tools": fake_tools}),
        patch("sensors.omni_parser.locate_element", return_value=None),
    ):
        result = hands_mod._handle_drag_element({"source": "knight", "target": "e4"})

    assert "source" in result.lower()
    assert "knight" in result


def test_drag_element_target_not_found():
    import coordinators.hands as hands_mod

    fake_mss, fake_tools = _install_fake_mss()
    source = {"label": "knight", "bbox": [10, 20, 30, 40], "center": [20, 30]}
    with (
        patch.dict(sys.modules, {"mss": fake_mss, "mss.tools": fake_tools}),
        patch("sensors.omni_parser.locate_element", side_effect=[source, None]),
    ):
        result = hands_mod._handle_drag_element({"source": "knight", "target": "e4"})

    assert "target" in result.lower()
    assert "e4" in result


def test_drag_element_both_found():
    import coordinators.hands as hands_mod

    fake_mss, fake_tools = _install_fake_mss()
    fake_pyautogui = MagicMock()
    source = {"label": "knight", "bbox": [10, 20, 30, 40], "center": [20, 30]}
    target = {"label": "e4", "bbox": [100, 120, 140, 160], "center": [120, 140]}
    with (
        patch.dict(sys.modules, {"mss": fake_mss, "mss.tools": fake_tools}),
        patch("sensors.omni_parser.locate_element", side_effect=[source, target]),
        patch.object(hands_mod, "pyautogui", fake_pyautogui),
    ):
        result = hands_mod._handle_drag_element({
            "source": "knight",
            "target": "e4",
            "duration": 0.2,
        })

    fake_pyautogui.dragTo.assert_called_once_with(120, 140, duration=0.2, button="left")
    assert result


def test_policy_locate_on_screen_is_whitelisted():
    from coordinators.hands_policy import classify_action

    decision = classify_action("locate_on_screen", {})

    assert decision.policy_class == "whitelist"


def test_policy_drag_to_is_greylisted():
    from coordinators.hands_policy import classify_action

    decision = classify_action("drag_to", {})

    assert decision.policy_class == "greylist"


def test_policy_drag_element_is_greylisted():
    from coordinators.hands_policy import classify_action

    decision = classify_action("drag_element", {})

    assert decision.policy_class == "greylist"
