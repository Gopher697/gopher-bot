# Codex Task — VLM Semantic Screen Description

## Context and Why This Matters

The VisionSensor now produces real structured perception: YOLO objects, EasyOCR text,
OpenCV motion. But the `description` field stored into memory is mechanical:

```
Window: "Stellaris" | Objects: monitor (0.91) | Text: "Fleet: 47", "Treasury: 2341"
```

This tells the bot *what is detectable* but not *what is happening*. The bot can't
distinguish a game world from a desktop app, understand that low Treasury in Stellaris
means a financial crisis is developing, or recognise that the text fragments visible in
the corner belong to an in-game HUD rather than a system UI. YOLO and EasyOCR have no
conceptual vocabulary for any of that.

A vision-language model (VLM) — e.g. Qwen2-VL loaded in LM Studio — can look at the
same screenshot and produce: "The user is playing Stellaris, a 4X space strategy game.
The star map view shows an ongoing fleet engagement. Treasury and energy indicators
appear critically low, with several alert notifications visible."

This task adds optional VLM semantic enrichment to the memory-storage path:

- The **live percept** (`VisionSensor.get_latest()`) keeps the mechanical description —
  always fast, no extra latency for Hands/Reason real-time use.
- The **stored observation** (`Memory.store_visual_observation()`) gets the enriched
  version: mechanical description + `| Scene: <vlm prose>` when a VLM is configured
  and available.

The VLM is **opt-in**: when `VISION_VLM_MODEL = ""` (the default), zero change in
behavior. When the user sets it to their loaded vision model name, enrichment fires
automatically on each significant-change storage event. If the LM Studio call fails
(wrong model loaded, timeout, unavailable), the sensor falls back silently to the
mechanical description — no hang, no crash.

**Files that change:**
1. `sensors/vision_sensor.py` — add VLM constants, `_grab_png_bytes()`,
   `_describe_with_vlm()`, update `_maybe_store_observation()` and `_start()` log

**Files that must NOT change:**
- `world_models/config.py`
- `world_models/graph.py`
- `coordinators/percepts.py`
- `coordinators/memory.py`
- `coordinators/sensory.py`
- `coordinators/reason.py`
- `coordinators/hands.py`
- `coordinators/hands_policy.py`
- `interface/server.py`

---

## Security invariant

Run `git status` before committing. If `world_models/config.py` appears, STOP.

---

## Changes to `sensors/vision_sensor.py`

The file currently has 423 lines. All changes are additive except one block update
to `_maybe_store_observation()` and one line update to `_start()`. Nothing else moves.

### 1. Add module-level import for OpenAI

Add immediately after the existing `import win32gui` line:

```python
from openai import OpenAI
```

`openai` is already a hard dependency (`requirements.txt`). This import at module scope
is required so tests can patch `sensors.vision_sensor.OpenAI`.

### 2. Add VLM constants (after the existing tuning-constants block)

Add these three constants immediately after the `OCR_CONFIDENCE = 0.50` line:

```python
# -- VLM semantic description (optional) --------------------------------------
# Set VISION_VLM_MODEL to the name of a vision-capable model loaded in LM Studio
# (e.g. "qwen2-vl-7b-instruct") to enable semantic scene descriptions in stored
# memory observations. Leave empty to disable — zero behavior change when unset.
VISION_VLM_MODEL: str = ""
VISION_VLM_BASE_URL: str = "http://localhost:1234/v1"
VISION_VLM_TIMEOUT: int = 30  # seconds; VLM inference on a desktop GPU is typically 5–20s
```

### 3. Add `_grab_png_bytes()` method to `VisionSensor`

Add immediately after the existing `_grab_frame()` method:

```python
def _grab_png_bytes(self) -> bytes | None:
    """
    Return the primary monitor screenshot as raw PNG bytes, or None on failure.

    This is a separate capture path from _grab_frame(): it uses mss.tools.to_png
    directly rather than converting to a numpy array, so it works even when numpy
    is not installed. Used exclusively for VLM calls — YOLO/OpenCV/EasyOCR still
    use the numpy frame from _grab_frame().
    """
    if self._sct is None:
        return None
    try:
        import mss.tools
        monitor = self._sct.monitors[1]
        sct_img = self._sct.grab(monitor)
        # to_png() returns bytes when output=None (the default)
        return mss.tools.to_png(sct_img.rgb, sct_img.size)
    except Exception as exc:
        logger.debug("PNG capture failed: %s", exc)
        return None
```

### 4. Add `_describe_with_vlm()` method to `VisionSensor`

Add immediately after `_grab_png_bytes()`:

```python
def _describe_with_vlm(self, png_bytes: bytes) -> str:
    """
    Send a desktop screenshot to the configured local VLM for semantic scene
    understanding. Returns a 2–3 sentence prose description, or empty string
    if VLM is not configured, png_bytes is empty, or the call fails.

    Uses LM Studio's OpenAI-compatible endpoint. The model must be a vision-
    capable model (e.g. Qwen2-VL) — a text-only model will return an error
    that is caught and logged at DEBUG level.

    This call is synchronous and may take 5–20 seconds. It is only invoked
    inside _maybe_store_observation(), which fires infrequently (on significant
    change events, minimum 60 s apart), so the sensor loop latency impact is
    acceptable.
    """
    if not VISION_VLM_MODEL or not png_bytes:
        return ""
    try:
        import base64
        encoded = base64.standard_b64encode(png_bytes).decode("utf-8")
        client = OpenAI(
            base_url=VISION_VLM_BASE_URL,
            api_key="lm-studio",
            timeout=VISION_VLM_TIMEOUT,
        )
        response = client.chat.completions.create(
            model=VISION_VLM_MODEL,
            max_tokens=256,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{encoded}"
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "Describe what is on this computer screen in 2-3 sentences. "
                                "Cover: what application or content is active, what the user "
                                "appears to be doing, and any important visible state such as "
                                "game status, document content, notifications, or media playing. "
                                "Be specific and factual."
                            ),
                        },
                    ],
                }
            ],
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.debug("VLM description failed: %s", exc)
        return ""
```

### 5. Replace `_maybe_store_observation()`

Replace the existing `_maybe_store_observation()` method (lines 347–370) with:

```python
def _maybe_store_observation(
    self,
    percept: VisualPercept,
    title: str,
) -> None:
    """
    Store the percept as a Memory observation if a significant change is detected.

    When VISION_VLM_MODEL is set and the VLM call succeeds, the stored observation
    is enriched with a semantic scene description appended to the mechanical one:
        'Window: "Stellaris" | Objects: ... | Scene: User is in a fleet battle...'

    The live percept (_latest_percept) is NOT mutated — it always keeps its fast
    mechanical description. Only the stored copy is enriched.

    Change-detection state updates only after successful storage.
    """
    if self._memory is None:
        return
    if not self._has_significant_change(
        title, percept.objects, percept.text_in_scene, percept.motion_detected
    ):
        return

    # Optionally enrich the stored copy with VLM semantic understanding.
    stored_percept = percept
    if VISION_VLM_MODEL:
        png_bytes = self._grab_png_bytes()
        vlm_desc = self._describe_with_vlm(png_bytes)
        if vlm_desc:
            from dataclasses import replace as _dc_replace
            stored_percept = _dc_replace(
                percept,
                description=f"{percept.description} | Scene: {vlm_desc}",
            )

    try:
        stored = self._memory.store_visual_observation(stored_percept)
        if stored:
            self._last_stored_ts = percept.timestamp
            self._stored_window_title = title
            self._stored_objects_key = ",".join(sorted(o.label for o in percept.objects))
            self._stored_text_key = ",".join(t.text for t in percept.text_in_scene)
    except Exception as exc:
        logger.debug("Failed to store visual observation: %s", exc)
```

### 6. Update `_start()` log line

Replace the existing `logger.info(...)` call inside `_start()` with:

```python
logger.info(
    "VisionSensor started (YOLO=%s, OpenCV=%s, EasyOCR=%s, VLM=%s)",
    _YOLO is not None,
    _cv2 is not None,
    _easyocr is not None,
    bool(VISION_VLM_MODEL),
)
```

---

## Tests (`tests/test_vision_vlmdescription.py`)

Create this new test file:

```python
"""Tests for VLM semantic scene description in VisionSensor."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import sensors.vision_sensor as vs_mod
from coordinators.percepts import VisualPercept
from sensors.vision_sensor import (
    VISION_VLM_BASE_URL,
    VISION_VLM_MODEL,
    VISION_VLM_TIMEOUT,
    VisionSensor,
)


# ── Constants ─────────────────────────────────────────────────────────────────

def test_vlm_constants_exist_and_are_correct_types():
    assert isinstance(VISION_VLM_MODEL, str)
    assert isinstance(VISION_VLM_BASE_URL, str)
    assert isinstance(VISION_VLM_TIMEOUT, int)
    assert VISION_VLM_TIMEOUT > 0


def test_vlm_model_defaults_to_empty_string():
    """Default must be empty so VLM path is opt-in."""
    assert VISION_VLM_MODEL == ""


# ── _grab_png_bytes ───────────────────────────────────────────────────────────

def test_grab_png_bytes_returns_none_without_sct():
    sensor = VisionSensor()
    sensor._sct = None
    assert sensor._grab_png_bytes() is None


def test_grab_png_bytes_returns_none_on_grab_failure():
    sensor = VisionSensor()
    sensor._sct = MagicMock()
    sensor._sct.grab.side_effect = RuntimeError("mss error")
    assert sensor._grab_png_bytes() is None


# ── _describe_with_vlm ────────────────────────────────────────────────────────

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
    """Any exception from LM Studio returns '' — no hang, no crash."""
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
    """VLM call uses base64-encoded PNG and the expected system prompt text."""
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

        # Image block with correct base64
        image_block = next(b for b in content if b.get("type") == "image_url")
        expected_b64 = base64.standard_b64encode(test_bytes).decode("utf-8")
        assert expected_b64 in image_block["image_url"]["url"]

        # Text block present
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


# ── _maybe_store_observation with VLM enrichment ─────────────────────────────

def test_maybe_store_observation_enriches_description_when_vlm_succeeds():
    """Stored observation includes mechanical + Scene: VLM prose."""
    original = vs_mod.VISION_VLM_MODEL
    vs_mod.VISION_VLM_MODEL = "qwen2-vl-test"
    try:
        sensor = VisionSensor()
        sensor._memory = MagicMock()
        sensor._memory.store_visual_observation.return_value = True
        sensor._last_stored_ts = 0.0  # force significant change

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
    """If VLM returns '' (model not loaded), mechanical description is stored as-is."""
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
    """_latest_percept must keep the mechanical description — only stored copy is enriched."""
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

        # The original percept object must be unchanged
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
```

---

## Verification

```
pytest tests/test_vision_vlmdescription.py -v
pytest tests/test_vision_sensor.py -v
pytest tests/test_vision_realvision.py -v
pytest --ignore=tests/test_graph.py --basetemp .tmp/pytest_vlm -v
```

Confirm `world_models/config.py` is not staged:
```
git status
```

Commit:
```
git commit -m "feat: VLM semantic scene description — enriches stored memory observations with vision-language model prose when configured"
```

---

## BACKLOG update (do after tests pass)

In `docs/BACKLOG.md`, add a new `✅` row for this feature immediately below the
VisionSensor row. Record the commit hash and the new test suite baseline count.

Also add a new `⬜` row for the next natural step:

```
| ⬜ OmniParser UI element detection | Replace YOLO (COCO real-world classes) with OmniParser for GUI-aware element detection: buttons, icons, interactive regions. Complements EasyOCR (text) and VLM (semantic). Fills the click-target gap for non-text UI elements. |
```
