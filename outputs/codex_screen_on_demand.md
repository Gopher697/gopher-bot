# Codex Task: On-demand screen capture + sensor self-awareness

## Problem

When a user asks "can you look at my screen?" the bot replies:
> "No. I don't have access to your screen."

Two gaps cause this:

1. **Sensory** never captures the screen on demand. It only falls back to
   `VisionSensor.get_latest()` (a background daemon frame that may be stale
   or absent). It has no trigger for user intent.

2. **Orientation** never mentions screen capability in the operational context
   header, so the bot genuinely believes it has no screen access.

## Goal

- When the user asks to see/look at the screen, Sensory grabs a fresh screenshot
  and routes it through the existing vision pipeline.
- Orientation lists active sensors in the operational header so the bot's
  self-model is accurate.

---

## Changes required

### 1. `coordinators/sensory.py`

#### 1a. Add a module-level screen-intent pattern

After the existing `SENSORY_TIMEOUT_SECONDS` constant, add:

```python
# Phrases that indicate the user wants the bot to look at the current screen.
_SCREEN_INTENT_RE = re.compile(
    r"(what.{0,15}(see|on.{0,10}screen|on.{0,10}monitor|on.{0,10}display|on.{0,10}desktop)"
    r"|look\s+at.{0,15}(screen|monitor|display|desktop)"
    r"|can\s+you\s+see"
    r"|see\s+my\s+screen"
    r"|your\s+screen"
    r"|my\s+screen)",
    re.IGNORECASE,
)
```

#### 1b. Add `_capture_screen()` helper

Add this function near the other private helpers at the bottom of the file
(before `_media_type_from_filename` or similar):

```python
def _capture_screen() -> bytes | None:
    """
    Capture all monitors as a single PNG using mss.

    Returns raw PNG bytes, or None if mss is not installed or capture fails.
    """
    try:
        import mss as _mss
        import mss.tools as _mss_tools
        with _mss.mss() as sct:
            # monitors[0] is the virtual screen covering all monitors combined.
            img = sct.grab(sct.monitors[0])
            return _mss_tools.to_png(img.rgb, img.size)
    except ImportError:
        logger.debug("mss not installed; on-demand screen capture unavailable")
        return None
    except Exception as exc:
        logger.warning("Screen capture failed: %s", exc)
        return None
```

#### 1c. Add on-demand capture block in `process()`

In `Sensory.process()`, locate the existing fallback block:

```python
        if "visual_percept" not in packet:
            latest_vp = VisionSensor.get_latest()
            if latest_vp:
                packet["visual_percept"] = latest_vp.to_dict()
```

Replace it with:

```python
        if "visual_percept" not in packet:
            message_text = str(packet.get("message", ""))
            if _SCREEN_INTENT_RE.search(message_text):
                # User explicitly asked to see the screen — capture fresh.
                png_bytes = _capture_screen()
                if png_bytes:
                    tier_config = get_tier_config(packet.get("tier", DEFAULT_TIER))
                    import time as _time_mod
                    if tier_config.get("base_url"):
                        # Local VLM: pass raw bytes to Reason as multimodal content.
                        encoded = base64.standard_b64encode(png_bytes).decode("utf-8")
                        packet["raw_images_for_reason"] = [{
                            "filename": "screen.png",
                            "media_type": "image/png",
                            "data_b64": encoded,
                        }]
                        packet["visual_percept"] = {
                            "timestamp": _time_mod.time(),
                            "objects": [],
                            "motion_detected": False,
                            "motion_region": None,
                            "scene_type": "on_demand_capture",
                            "text_in_scene": [],
                            "faces_detected": 0,
                            "pose_summary": "",
                            "description": "",
                        }
                    else:
                        # Cloud tier: pre-describe via Anthropic vision API.
                        desc = _describe_image(
                            png_bytes, "screen.png", tier_config
                        )
                        packet["visual_percept"] = {
                            "timestamp": _time_mod.time(),
                            "objects": [],
                            "motion_detected": False,
                            "motion_region": None,
                            "scene_type": "on_demand_capture",
                            "text_in_scene": [],
                            "faces_detected": 0,
                            "pose_summary": "",
                            "description": desc or "(screen captured; description unavailable)",
                        }
            else:
                # No screen intent — use background VisionSensor frame if available.
                latest_vp = VisionSensor.get_latest()
                if latest_vp:
                    packet["visual_percept"] = latest_vp.to_dict()
```

---

### 2. `coordinators/orientation.py`

#### 2a. Add module-level sensor availability cache

After the existing imports, add:

```python
import importlib as _importlib

def _sensor_available(module_name: str) -> bool:
    """Return True if module_name can be imported (cached by importlib)."""
    try:
        _importlib.import_module(module_name)
        return True
    except ImportError:
        return False
```

#### 2b. Add sensor status to `_operational_context()`

In `_operational_context(packet, now_ts)`, after the `autonomous` block and
before the final `return`, add:

```python
    # Active sensor capabilities — informs the bot's self-model.
    sensor_labels: list[str] = []
    if _sensor_available("mss"):
        sensor_labels.append("screen-capture")
    try:
        from sensors.vision_sensor import VisionSensor as _VS
        if _VS.get_latest() is not None:
            sensor_labels.append("screen-memory")
    except Exception:
        pass
    if sensor_labels:
        parts.append(f"Sensors active: {', '.join(sensor_labels)}")
```

---

### 3. `tests/test_screen_on_demand.py` — new test file

```
test_screen_intent_detected_for_look_at_screen:
    Assert _SCREEN_INTENT_RE.search("Can you look at my screen?") is not None.

test_screen_intent_detected_for_what_do_you_see:
    Assert _SCREEN_INTENT_RE.search("What do you see on my screen?") is not None.

test_screen_intent_not_detected_for_normal_message:
    Assert _SCREEN_INTENT_RE.search("What is the capital of France?") is None.

test_capture_screen_returns_none_when_mss_missing:
    Patch mss import to raise ImportError.
    Call _capture_screen().
    Assert result is None.

test_capture_screen_returns_bytes_when_mss_available:
    Patch mss.mss() context manager to return a fake sct object with
    sct.monitors = [{"left": 0, "top": 0, "width": 100, "height": 100}]
    and sct.grab() returning a fake image.
    Patch mss.tools.to_png to return b"fakepng".
    Call _capture_screen().
    Assert result == b"fakepng".

test_sensory_on_demand_capture_local_tier:
    Patch _capture_screen to return b"fakepng".
    Patch get_tier_config to return {"base_url": "http://localhost:1234/v1"}.
    Build packet with message="What do you see on my screen?" and tier=TIER_LOCAL.
    Call Sensory().process(packet).
    Assert "raw_images_for_reason" in result.
    Assert result["visual_percept"]["scene_type"] == "on_demand_capture".

test_sensory_no_capture_for_normal_message:
    Patch _capture_screen to return b"fakepng".
    Build packet with message="What is the capital of France?".
    Ensure _capture_screen is NOT called (use MagicMock assert_not_called).

test_operational_context_includes_screen_sensor:
    Patch _sensor_available("mss") to return True.
    Patch VisionSensor.get_latest() to return None.
    Call _operational_context({}, time.time()).
    Assert "screen-capture" in result.

test_operational_context_no_sensor_when_mss_missing:
    Patch _sensor_available("mss") to return False.
    Patch VisionSensor.get_latest() to return None.
    Call _operational_context({}, time.time()).
    Assert "Sensors" not in result.
```

---

## Acceptance criteria

```
pytest tests/test_screen_on_demand.py -v   # all new tests pass
pytest --basetemp .tmp/pytest-tmp -q        # full suite still passes
```

Then restart the bot and send "Can you look at my screen?" via Discord.
The bot should capture a fresh screenshot and describe what it sees.

## Commit instructions

```
git add coordinators/sensory.py coordinators/orientation.py tests/test_screen_on_demand.py
git reset HEAD world_models/config.py
git commit -m "feat: on-demand screen capture + sensor self-awareness

- Sensory: detect screen-intent phrases and capture fresh screenshot via mss
  when user asks to see the screen; routes through existing vision pipeline
  (local VLM multimodal or cloud Anthropic description path)
- Orientation: _operational_context() now reports active sensors (screen-capture,
  screen-memory) so bot's self-model accurately reflects capabilities
- 8 new tests in tests/test_screen_on_demand.py"
git push origin main
```

## Security reminder

Do not stage or commit `world_models/config.py`.
