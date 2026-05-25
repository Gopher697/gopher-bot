"""Tests for real VisionSensor: YOLO + OpenCV + EasyOCR + memory integration."""
from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

from coordinators.percepts import TextSegment, VisualObject, VisualPercept
from sensors.vision_sensor import (
    MAX_OBJECTS,
    MAX_TEXT_ITEMS,
    VISION_MIN_SNAPSHOT_SECONDS,
    VisionSensor,
    _build_description_fn,
    _has_significant_change_fn,
)


# -- _build_description_fn ----------------------------------------------------

def test_build_description_window_only():
    result = _build_description_fn("Notepad", [], [], False)
    assert "Notepad" in result
    assert "Window:" in result


def test_build_description_with_objects():
    objects = [VisualObject(label="keyboard", confidence=0.9, bbox=[0, 0, 100, 100])]
    result = _build_description_fn("", objects, [], False)
    assert "keyboard" in result
    assert "0.90" in result


def test_build_description_with_text():
    segs = [TextSegment(text="Submit", position=[10, 20, 80, 40])]
    result = _build_description_fn("", [], segs, False)
    assert "Submit" in result
    assert "Text:" in result


def test_build_description_motion():
    result = _build_description_fn("", [], [], True)
    assert "Motion" in result


def test_build_description_empty_returns_fallback():
    result = _build_description_fn("", [], [], False)
    assert result
    assert "no content" in result.lower()


def test_build_description_caps_objects_display():
    objects = [
        VisualObject(label=f"item{i}", confidence=0.9 - i * 0.01, bbox=[0, 0, 1, 1])
        for i in range(12)
    ]
    result = _build_description_fn("", objects, [], False)
    assert "+6 more" in result


# -- _has_significant_change_fn ----------------------------------------------

def test_change_triggers_on_min_interval_elapsed():
    old_ts = time.time() - VISION_MIN_SNAPSHOT_SECONDS - 1
    assert _has_significant_change_fn(
        "Win", [], [], False, "Win", "", "", old_ts
    ) is True


def test_change_triggers_on_window_switch():
    recent = time.time() - 5
    assert _has_significant_change_fn(
        "NewWin", [], [], False, "OldWin", "", "", recent
    ) is True


def test_change_triggers_on_motion():
    recent = time.time() - 5
    assert _has_significant_change_fn(
        "Win", [], [], True, "Win", "", "", recent
    ) is True


def test_no_change_when_identical():
    recent = time.time() - 5
    objects = [VisualObject(label="cat", confidence=0.9, bbox=[0, 0, 1, 1])]
    text = [TextSegment(text="hello", position=[0, 0, 1, 1])]
    result = _has_significant_change_fn(
        "Win", objects, text, False, "Win", "cat", "hello", recent
    )
    assert result is False


def test_change_triggers_on_new_objects():
    recent = time.time() - 5
    objects = [VisualObject(label="dog", confidence=0.9, bbox=[0, 0, 1, 1])]
    assert _has_significant_change_fn(
        "Win", objects, [], False, "Win", "cat", "", recent
    ) is True


def test_change_triggers_on_many_new_text_items():
    recent = time.time() - 5
    text_segs = [TextSegment(text=f"item{i}", position=[0, 0, 1, 1]) for i in range(5)]
    assert _has_significant_change_fn(
        "Win", [], text_segs, False, "Win", "", "", recent
    ) is True


# -- VisionSensor._detect_objects --------------------------------------------

def test_detect_objects_returns_empty_without_yolo():
    sensor = VisionSensor()
    sensor._yolo = None
    result = sensor._detect_objects(MagicMock())
    assert result == []


def test_detect_objects_returns_empty_without_frame():
    sensor = VisionSensor()
    result = sensor._detect_objects(None)
    assert result == []


def test_detect_objects_caps_at_max_objects():
    sensor = VisionSensor()
    fake_box = MagicMock()
    fake_box.cls = [0]
    fake_box.conf = [0.9]
    fake_box.xyxy = [[0.0, 0.0, 100.0, 100.0]]
    fake_result = MagicMock()
    fake_result.boxes = [fake_box] * (MAX_OBJECTS + 5)
    fake_result.names = {0: "cat"}
    sensor._yolo = MagicMock(return_value=[fake_result])
    result = sensor._detect_objects(MagicMock())
    assert len(result) <= MAX_OBJECTS


# -- VisionSensor._detect_text ------------------------------------------------

def test_detect_text_returns_empty_without_reader():
    sensor = VisionSensor()
    sensor._reader = None
    result = sensor._detect_text(MagicMock())
    assert result == []


def test_detect_text_filters_low_confidence():
    sensor = VisionSensor()
    sensor._reader = MagicMock()
    sensor._reader.readtext.return_value = [
        ([[0, 0], [10, 0], [10, 10], [0, 10]], "hello", 0.9),
        ([[0, 0], [10, 0], [10, 10], [0, 10]], "noise", 0.1),
    ]
    result = sensor._detect_text(MagicMock())
    texts = [seg.text for seg in result]
    assert "hello" in texts
    assert "noise" not in texts


def test_detect_text_caps_at_max_items():
    sensor = VisionSensor()
    fake_results = [
        ([[0, 0], [1, 0], [1, 1], [0, 1]], f"text{i}", 0.9)
        for i in range(MAX_TEXT_ITEMS + 10)
    ]
    sensor._reader = MagicMock()
    sensor._reader.readtext.return_value = fake_results
    result = sensor._detect_text(MagicMock())
    assert len(result) <= MAX_TEXT_ITEMS


# -- VisionSensor._detect_motion ---------------------------------------------

def test_detect_motion_returns_false_on_first_frame():
    sensor = VisionSensor()
    sensor._prev_frame = None
    detected, region = sensor._detect_motion(None)
    assert detected is False
    assert region is None


# -- Memory.store_visual_observation -----------------------------------------

def test_store_visual_observation_calls_store_with_perceived():
    from coordinators.memory import Memory

    memory = Memory()
    memory.store = MagicMock()
    percept = VisualPercept(
        timestamp=1000.0,
        description='Window: "Notepad" | Text: "hello"',
        scene_type="desktop",
    )

    result = memory.store_visual_observation(percept)

    assert result is True
    memory.store.assert_called_once()
    assert memory.store.call_args.kwargs.get("source_type") == "perceived"


def test_store_visual_observation_returns_false_for_empty_description():
    from coordinators.memory import Memory

    memory = Memory()
    memory.store = MagicMock()
    percept = VisualPercept(timestamp=1000.0, description="", scene_type="desktop")

    result = memory.store_visual_observation(percept)

    assert result is False
    memory.store.assert_not_called()


# -- Hands: click_label -------------------------------------------------------

def test_click_label_finds_text_segment():
    import coordinators.hands as hands_mod

    fake_percept = MagicMock()
    fake_percept.text_in_scene = [
        TextSegment(text="Submit", position=[100.0, 200.0, 200.0, 230.0])
    ]
    fake_percept.objects = []

    with patch("coordinators.hands.VisionSensor") as MockVS:
        MockVS.get_latest.return_value = fake_percept
        with patch("coordinators.hands.pyautogui") as mock_pag:
            result = hands_mod._handle_click_label({"label": "submit"})

    assert "Submit" in result
    assert "150" in result
    mock_pag.click.assert_called_once_with(150, 215)


def test_click_label_returns_error_when_no_percept():
    import coordinators.hands as hands_mod

    with patch("coordinators.hands.VisionSensor") as MockVS:
        MockVS.get_latest.return_value = None
        result = hands_mod._handle_click_label({"label": "ok"})
    assert "Error" in result


def test_click_label_returns_not_found_when_no_match():
    import coordinators.hands as hands_mod

    fake_percept = MagicMock()
    fake_percept.text_in_scene = [
        TextSegment(text="Cancel", position=[0.0, 0.0, 50.0, 20.0])
    ]
    fake_percept.objects = []

    with patch("coordinators.hands.VisionSensor") as MockVS:
        MockVS.get_latest.return_value = fake_percept
        result = hands_mod._handle_click_label({"label": "submit"})
    assert "No element" in result


# -- Hands: get_visible_elements ---------------------------------------------

def test_get_visible_elements_returns_json():
    import coordinators.hands as hands_mod

    fake_percept = MagicMock()
    fake_percept.text_in_scene = [
        TextSegment(text="File", position=[0.0, 0.0, 40.0, 20.0])
    ]
    fake_percept.objects = [
        VisualObject(label="monitor", confidence=0.88, bbox=[0.0, 0.0, 1920.0, 1080.0])
    ]

    with patch("coordinators.hands.VisionSensor") as MockVS:
        MockVS.get_latest.return_value = fake_percept
        result = hands_mod._handle_get_visible_elements({})

    data = json.loads(result)
    assert any(item["text"] == "File" for item in data["text_labels"])
    assert any(item["label"] == "monitor" for item in data["object_labels"])


def test_get_visible_elements_empty_when_no_percept():
    import coordinators.hands as hands_mod

    with patch("coordinators.hands.VisionSensor") as MockVS:
        MockVS.get_latest.return_value = None
        result = hands_mod._handle_get_visible_elements({})

    data = json.loads(result)
    assert data["text_labels"] == []
    assert data["object_labels"] == []


# -- Reason: visual context expansion ----------------------------------------

def test_reason_appends_element_labels_for_desktop_percept():
    from coordinators.reason import Reason

    reason = Reason()
    captured_system_prompts = []

    def fake_local_reasoner(message, system_prompt, tier_config, **kwargs):
        captured_system_prompts.append(system_prompt)
        fake = MagicMock()
        fake.choices = [MagicMock(message=MagicMock(content="ok"))]
        return fake

    import coordinators.reason as reason_mod

    with patch.object(reason_mod, "_call_local_reasoner", fake_local_reasoner):
        packet = {
            "message": "click the submit button",
            "memory_context": "",
            "tier": 1,
            "visual_percept": {
                "scene_type": "desktop",
                "description": 'Window: "Chrome"',
                "text_in_scene": [{"text": "Submit", "position": [0, 0, 1, 1]}],
                "objects": [],
            },
        }
        reason.process(packet)

    assert captured_system_prompts
    assert "Submit" in captured_system_prompts[0]
    assert "Visible elements" in captured_system_prompts[0]


def test_reason_does_not_append_elements_for_user_attachment():
    from coordinators.reason import Reason

    reason = Reason()
    captured = []

    def fake_local_reasoner(message, system_prompt, tier_config, **kwargs):
        captured.append(system_prompt)
        fake = MagicMock()
        fake.choices = [MagicMock(message=MagicMock(content="ok"))]
        return fake

    import coordinators.reason as reason_mod

    with patch.object(reason_mod, "_call_local_reasoner", fake_local_reasoner):
        packet = {
            "message": "what is in this image?",
            "memory_context": "",
            "tier": 1,
            "visual_percept": {
                "scene_type": "user_attachment",
                "description": "[photo.jpg]: A cat sitting on a keyboard",
                "text_in_scene": [],
                "objects": [],
            },
        }
        reason.process(packet)

    assert "Visible elements" not in captured[0]
