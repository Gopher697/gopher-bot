# Codex Task 68 — Discord Image Attachments via Sensory Vision Path

## Context

The Discord bridge (`interface/discord_bot.py`) is the new primary user interface for
Gopher-bot. Users will send images — screenshots, photos, documents — directly in Discord.
The architecture requires that the bridge stay thin: it passes data to Awareness and the
coordinator pipeline handles everything else.

Image description must go through the existing Sensory coordinator using the model already
designated for that tier in `tier_config.py`. At TIER_STANDARD and TIER_ENHANCED, the
`sensory_model` is `claude-haiku-4-5-20251001` which supports vision natively via the
Anthropic API. At TIER_LOCAL the sensory model is a local LLM with no vision capability —
fall back gracefully to a note with no description.

**Do not introduce any new model selection logic.** Use `tier_config["sensory_model"]`
and `tier_config["base_url"]` exactly as the rest of Sensory does: `base_url is None`
means Anthropic cloud (vision-capable); `base_url` set means local (skip vision).

---

## Security invariant — check before every commit

`world_models/config.py` is gitignored and contains Neo4j credentials and API keys.
Run `git status` before committing. If `world_models/config.py` appears, STOP — do not commit.

---

## Part 1: Extend `VisualPercept` in `coordinators/percepts.py`

Add one field to the `VisualPercept` dataclass:

```python
description: str = ""   # LLM-generated prose description of the image
```

Place it after `pose_summary`. Also extend `to_dict` and `from_dict` to include it:

In `to_dict`:
```python
"description": self.description,
```

In `from_dict`:
```python
description=str(data.get("description", "")),
```

---

## Part 2: Image vision helper in `coordinators/sensory.py`

Add this import at the top of the file:
```python
import base64
from pathlib import Path as _Path
```

Add this private helper function (place it near `_call_anthropic_classifier`):

```python
def _media_type_from_filename(filename: str) -> str:
    ext = _Path(filename).suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }.get(ext, "image/jpeg")


def _describe_image(image_data: bytes, filename: str, tier_config: dict) -> str:
    """
    Generate a prose description of an image using the tier's sensory model.
    Returns an empty string if the tier is local (no vision) or if the call fails.
    Vision is only available when base_url is None (Anthropic cloud).
    """
    if tier_config.get("base_url"):
        # Local model — no vision capability
        return ""
    model = tier_config.get("sensory_model")
    if not model:
        return ""
    try:
        client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
        media_type = _media_type_from_filename(filename)
        encoded = base64.standard_b64encode(image_data).decode("utf-8")
        response = client.messages.create(
            model=model,
            max_tokens=512,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": encoded,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Describe this image concisely as a factual note. "
                                "Cover what is shown, any visible text, and any context "
                                "relevant to a work log or memory system. "
                                "Two to four sentences maximum."
                            ),
                        },
                    ],
                }
            ],
        )
        return _extract_text(response).strip()
    except Exception as e:
        logger.warning("Image description failed for %s: %s", filename, e)
        return ""
```

---

## Part 3: Call the vision helper from `Sensory.process()`

In `Sensory.process()`, add the following block **before** the existing
`if "visual_percept" not in packet:` check (so user-attached images take
precedence over the live VisionSensor feed):

```python
# Handle image attachments from the Discord bridge (or any future input source).
# Each entry is {"filename": str, "data": bytes}.
image_attachments = packet.pop("image_attachments", None) or []
if image_attachments and "visual_percept" not in packet:
    tier_config = get_tier_config(packet.get("tier", DEFAULT_TIER))
    descriptions = []
    for attachment in image_attachments:
        filename = attachment.get("filename", "image")
        data = attachment.get("data", b"")
        if not data:
            continue
        desc = _describe_image(data, filename, tier_config)
        if desc:
            descriptions.append(f"[{filename}]: {desc}")
        else:
            descriptions.append(f"[{filename}]: (image attached; no description available at current tier)")
    if descriptions:
        combined_description = "\n".join(descriptions)
        import time as _time_mod
        packet["visual_percept"] = {
            "timestamp": _time_mod.time(),
            "objects": [],
            "motion_detected": False,
            "motion_region": None,
            "scene_type": "user_attachment",
            "text_in_scene": [],
            "faces_detected": 0,
            "pose_summary": "",
            "description": combined_description,
        }
```

---

## Part 4: Update `interface/discord_bot.py`

Replace the existing `_image_attachment_note()` function and the block in `on_message`
that calls it with the following approach:

### Remove `_image_attachment_note()`
Delete the entire `_image_attachment_note` function.

### Add `_download_image_attachments()` 

```python
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".bmp"}


async def _download_image_attachments(message: discord.Message) -> list[dict]:
    """
    Download image attachments and return them as a list of
    {"filename": str, "data": bytes} dicts for the Sensory coordinator.
    Skips files over MAX_ATTACHMENT_BYTES.
    """
    result = []
    for attachment in message.attachments:
        suffix = Path(attachment.filename or "").suffix.lower()
        if suffix not in IMAGE_EXTENSIONS:
            continue
        if attachment.size and attachment.size > MAX_ATTACHMENT_BYTES:
            print(f"[discord] Skipping oversized image: {attachment.filename}")
            continue
        try:
            data = await attachment.read()
            result.append({"filename": attachment.filename, "data": data})
        except Exception as exc:
            print(f"[discord] Failed to download {attachment.filename}: {exc}")
    return result
```

### Update `on_message` 

Replace the `image_note = _image_attachment_note(message)` lines with:

```python
image_attachments = await _download_image_attachments(message)
```

And update the `synchronous_run` call to pass the attachments as a packet override:

```python
async with message.channel.typing():
    packet = await asyncio.to_thread(
        bot.awareness.synchronous_run,
        content,
        image_attachments=image_attachments,
    )
```

Remove the `if image_note: content = ...` block entirely — the description now
flows through the Sensory coordinator, not through the message text.

---

## Part 5: Tests — `tests/test_discord_image_vision.py`

Create this new test file:

```python
"""
Tests for the Discord image attachment → Sensory vision path.
"""
from __future__ import annotations

import base64
import time
from unittest.mock import MagicMock, patch

import pytest

from coordinators.percepts import VisualPercept
from coordinators.sensory import Sensory, _describe_image, _media_type_from_filename
from coordinators.tier_config import TIER_LOCAL, TIER_STANDARD, get_tier_config


# ── _media_type_from_filename ───────────────────────────────────────────────

def test_media_type_jpg():
    assert _media_type_from_filename("photo.jpg") == "image/jpeg"

def test_media_type_jpeg():
    assert _media_type_from_filename("photo.jpeg") == "image/jpeg"

def test_media_type_png():
    assert _media_type_from_filename("screenshot.png") == "image/png"

def test_media_type_unknown_defaults_to_jpeg():
    assert _media_type_from_filename("file.bmp") == "image/jpeg"


# ── _describe_image ─────────────────────────────────────────────────────────

def test_describe_image_returns_empty_for_local_tier():
    """Local tier has base_url set — vision is skipped, returns empty string."""
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


# ── Sensory.process with image_attachments ──────────────────────────────────

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
    with patch("coordinators.sensory._describe_image", return_value="A desktop screenshot."):
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
    with patch("coordinators.sensory._describe_image", return_value="A test image."):
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


# ── VisualPercept schema ─────────────────────────────────────────────────────

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
```

---

## Verification

```
pytest tests/test_discord_image_vision.py --basetemp .tmp/pytest_codex_task68 -v
pytest --ignore=tests/test_graph.py --basetemp .tmp/pytest_codex_task68 -v
```

Confirm `world_models/config.py` is NOT staged:
```
git status
```

Commit:
```
git commit -m "feat: Discord image attachments routed through Sensory vision path (Task 68)"
```

---

## Summary of changes

| File | Change |
|---|---|
| `coordinators/percepts.py` | Add `description: str = ""` to `VisualPercept`; extend `to_dict` and `from_dict` |
| `coordinators/sensory.py` | Add `_media_type_from_filename()` and `_describe_image()` helpers; update `process()` to handle `image_attachments` packet key |
| `interface/discord_bot.py` | Replace `_image_attachment_note()` with `_download_image_attachments()`; pass image bytes as `image_attachments` packet override to `synchronous_run` |
| `tests/test_discord_image_vision.py` | New test file — 11 tests covering schema, helpers, and the full Sensory path |
