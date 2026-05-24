"""
Tests for the Discord image attachment -> Sensory vision path.
"""
from __future__ import annotations

import base64
import time
from unittest.mock import MagicMock, patch

import pytest

from coordinators.percepts import VisualPercept
from coordinators.sensory import Sensory, _describe_image, _media_type_from_filename
from coordinators.tier_config import TIER_LOCAL, TIER_STANDARD, get_tier_config


# -- _media_type_from_filename ----------------------------------------------

def test_media_type_jpg():
    assert _media_type_from_filename("photo.jpg") == "image/jpeg"


def test_media_type_jpeg():
    assert _media_type_from_filename("photo.jpeg") == "image/jpeg"


def test_media_type_png():
    assert _media_type_from_filename("screenshot.png") == "image/png"


def test_media_type_unknown_defaults_to_jpeg():
    assert _media_type_from_filename("file.bmp") == "image/jpeg"


# -- _describe_image ---------------------------------------------------------

def test_describe_image_returns_empty_for_local_tier():
    """Local tier has base_url set - vision is skipped, returns empty string."""
    local_config = get_tier_config(TIER_LOCAL)
    result = _describe_image(b"fake_image_bytes", "test.png", local_config)
    assert result == ""


def test_describe_image_returns_empty_on_api_failure():
    """If the Anthropic call raises, returns empty string without propagating."""
    standard_config = get_tier_config(TIER_STANDARD)
    with patch("coordinators.sensory.Anthropic") as mock_anthropic:
        mock_anthropic.return_value.messages.create.side_effect = RuntimeError("API down")
        result = _describe_image(b"fake", "photo.png", standard_config)
    assert result == ""


def test_describe_image_returns_description_on_success():
    """Happy path: Anthropic returns a description, function returns it."""
    standard_config = get_tier_config(TIER_STANDARD)
    mock_response = MagicMock()
    mock_response.choices = None
    mock_response.content = [MagicMock(text="A hallway with a wet floor sign.")]
    with patch("coordinators.sensory.Anthropic") as mock_anthropic:
        mock_anthropic.return_value.messages.create.return_value = mock_response
        result = _describe_image(b"fake", "hallway.jpg", standard_config)
    assert "hallway" in result.lower() or "floor" in result.lower() or result != ""


# -- Sensory.process with image_attachments ---------------------------------

def test_sensory_processes_image_attachments_into_visual_percept():
    """
    When image_attachments is in the packet and tier supports vision,
    Sensory should produce a visual_percept with scene_type='user_attachment'.
    """
    sensory = Sensory()
    fake_bytes = b"\x89PNG\r\n\x1a\n"  # PNG magic bytes
    packet = {
        "message": "here is a screenshot",
        "tier": TIER_STANDARD,
        "image_attachments": [{"filename": "screen.png", "data": fake_bytes}],
    }
    mock_resp = MagicMock()
    mock_resp.choices = None
    mock_resp.content = [MagicMock(text='{"intent": "share", "keywords": ["screenshot"]}')]
    with (
        patch("coordinators.sensory._describe_image", return_value="A desktop screenshot."),
        patch("coordinators.sensory._call_anthropic_classifier", return_value=mock_resp),
    ):
        result = sensory.process(packet)

    assert "visual_percept" in result
    assert result["visual_percept"]["scene_type"] == "user_attachment"
    assert "screen.png" in result["visual_percept"]["description"]


def test_sensory_image_attachments_key_removed_from_packet():
    """image_attachments should be popped from packet (not passed downstream)."""
    sensory = Sensory()
    packet = {
        "message": "check this",
        "tier": TIER_STANDARD,
        "image_attachments": [{"filename": "test.jpg", "data": b"fake"}],
    }
    mock_resp = MagicMock()
    mock_resp.choices = None
    mock_resp.content = [MagicMock(text='{"intent": "share", "keywords": ["test"]}')]
    with (
        patch("coordinators.sensory._describe_image", return_value="A test image."),
        patch("coordinators.sensory._call_anthropic_classifier", return_value=mock_resp),
    ):
        result = sensory.process(packet)
    assert "image_attachments" not in result


def test_sensory_skips_vision_at_local_tier():
    """
    At TIER_LOCAL, _describe_image returns "" and the fallback note is used.
    A visual_percept is still created but description notes no description available.
    """
    sensory = Sensory()
    packet = {
        "message": "look at this",
        "tier": TIER_LOCAL,
        "image_attachments": [{"filename": "photo.jpg", "data": b"fake"}],
    }
    mock_resp = MagicMock()
    mock_resp.choices = [
        MagicMock(message=MagicMock(content='{"intent": "share", "keywords": ["photo"]}'))
    ]
    with patch("coordinators.sensory._call_local_classifier", return_value=mock_resp):
        result = sensory.process(packet)
    assert "visual_percept" in result
    vp = result["visual_percept"]
    assert vp["scene_type"] == "user_attachment"
    assert "no description available" in vp["description"]


def test_sensory_no_image_attachments_falls_through_normally():
    """When no image_attachments present, Sensory runs its normal text path."""
    sensory = Sensory()
    packet = {"message": "what time is it", "tier": TIER_STANDARD}
    with patch("coordinators.sensory._call_anthropic_classifier") as mock_call:
        mock_resp = MagicMock()
        mock_resp.choices = None
        mock_resp.content = [MagicMock(text='{"intent": "query", "keywords": ["time"]}')]
        mock_call.return_value = mock_resp
        result = sensory.process(packet)
    assert "intent" in result
    assert "visual_percept" not in result or result.get("visual_percept", {}).get("scene_type") != "user_attachment"


# -- VisualPercept schema ----------------------------------------------------

def test_visual_percept_description_field_roundtrips():
    vp = VisualPercept(
        timestamp=time.time(),
        description="A photo of a wet floor in the hallway near room 204.",
    )
    d = vp.to_dict()
    assert d["description"] == "A photo of a wet floor in the hallway near room 204."
    restored = VisualPercept.from_dict(d)
    assert restored.description == vp.description


def test_visual_percept_description_defaults_to_empty():
    vp = VisualPercept(timestamp=0.0)
    assert vp.description == ""
    d = vp.to_dict()
    assert "description" in d
    restored = VisualPercept.from_dict({})
    assert restored.description == ""
