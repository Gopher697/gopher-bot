# Codex Task — Real VisionSensor: YOLO + OpenCV + EasyOCR + Memory Integration

## Context and Why This Matters

`sensors/vision_sensor.py` is currently a stub. It grabs a screenshot and reads the
foreground window title — nothing more. `VisualPercept.objects` is always `[]`,
`text_in_scene` contains only the window title, `motion_detected` is always `False`,
and `description` is always `""`.

The `VisualPercept` dataclass in `coordinators/percepts.py` was designed from the
start to carry real computer-vision output: bounding boxes from YOLO, OCR text with
positions, motion regions from OpenCV. All those fields exist and are wired into
`Sensory`, `Memory`, and `Reason` — they just receive empty data because the sensor
doesn't fill them.

This task replaces the stub with a real perception loop and wires visual snapshots
into the memory system so the bot builds a persistent, searchable record of what
it sees over time.

**The four goals:**

1. **Real perception** — YOLO v8 nano for object detection, OpenCV for motion
   detection, EasyOCR for on-screen text. All imports are optional; degrade
   gracefully if the `[vision]` extras are not installed.

2. **Memory integration** — Add `Memory.store_visual_observation()`. When the
   VisionSensor detects a significant change (window switch, motion, new objects,
   or the minimum snapshot interval has elapsed), store the percept as a graph
   Observation with `source_type="perceived"`.

3. **Hands label-clicking** — Add `click_label` and `get_visible_elements` actions
   to `coordinators/hands.py` so the bot can click UI elements by visible label
   instead of needing to know pixel coordinates in advance.

4. **Reason context expansion** — Update `Reason.process()` to append the list of
   currently visible element labels (from EasyOCR + YOLO) to the visual context
   string it passes to the LLM, so Reason can reference and act on what is on screen.

**Files that change:**
1. `sensors/vision_sensor.py` — full replacement
2. `coordinators/memory.py` — add `store_visual_observation()` method
3. `coordinators/hands.py` — add `click_label` and `get_visible_elements` handlers
4. `coordinators/reason.py` — update `process()` visual context assembly

**Files that must NOT change:**
- `world_models/config.py`
- `world_models/graph.py`
- `coordinators/percepts.py` (schema is already correct)
- `coordinators/sensory.py` (image description path is unchanged)
- `coordinators/embedder.py`

---

## Security invariant

Run `git status` before committing. If `world_models/config.py` appears, STOP.

---

## Part 1 — `sensors/vision_sensor.py`

Replace the entire file with the implementation below.

### Constants and optional imports

```python
from __future__ import annotations

import logging
import threading
import time

import win32gui

from coordinators.percepts import TextSegment, VisualObject, VisualPercept

logger = logging.getLogger(__name__)

# ── Optional heavy imports — degrade gracefully without [vision] extras ────────

try:
    import numpy as _np
except ImportError:
    _np = None

try:
    from ultralytics import YOLO as _YOLO
except ImportError:
    _YOLO = None

try:
    import cv2 as _cv2
except ImportError:
    _cv2 = None

try:
    import easyocr as _easyocr
except ImportError:
    _easyocr = None

try:
    import mss as _mss
except ImportError:
    _mss = None

# ── Tuning constants ────────────────────────────────────────────────────────────

VISION_TICK_SECONDS = 2.0          # main loop interval; EasyOCR needs ~500ms on CPU
VISION_OCR_INTERVAL_TICKS = 5     # run EasyOCR every N ticks (~10 s at default tick)
VISION_MIN_SNAPSHOT_SECONDS = 60  # always store a percept at least this often
YOLO_MODEL = "yolov8n.pt"         # nano model — fast; auto-downloads on first use
YOLO_CONFIDENCE = 0.40            # minimum confidence to keep a detection
MAX_OBJECTS = 10                  # cap YOLO results by confidence (descending)
MAX_TEXT_ITEMS = 20               # cap EasyOCR results
OCR_CONFIDENCE = 0.50             # minimum EasyOCR confidence

# ── Module-level state ──────────────────────────────────────────────────────────

_latest_percept: VisualPercept | None = None
_percept_lock = threading.Lock()
```

### `VisionSensor` class

```python
class VisionSensor:
    """
    Singleton background thread that produces VisualPercept snapshots.

    Uses YOLO v8 for object detection, OpenCV for motion detection, and
    EasyOCR for on-screen text recognition. All heavy libraries are optional
    imports — if not installed, each capability silently degrades to empty
    output while the window-title path continues to function.

    Call VisionSensor.configure(memory=<Memory instance>) once at startup
    before calling VisionSensor.start(). Memory storage is skipped if no
    Memory instance has been configured.
    """

    _instance: VisionSensor | None = None

    # ── Singleton interface ─────────────────────────────────────────────────

    @classmethod
    def get_instance(cls) -> VisionSensor:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def configure(cls, memory=None) -> None:
        """
        Provide a Memory coordinator instance for storing visual observations.
        Call this once at startup, before VisionSensor.start().
        """
        cls.get_instance()._memory = memory

    @classmethod
    def start(cls) -> None:
        cls.get_instance()._start()

    @classmethod
    def stop(cls) -> None:
        cls.get_instance()._stop()

    @classmethod
    def get_latest(cls) -> VisualPercept | None:
        with _percept_lock:
            return _latest_percept

    # ── Construction ────────────────────────────────────────────────────────

    def __init__(self) -> None:
        self.running = False
        self.thread: threading.Thread | None = None

        # Screen capture
        self._sct = None

        # Lazy-loaded models
        self._yolo = None
        self._reader = None
        self._models_loaded = False

        # Motion detection state
        self._prev_frame = None  # grayscale numpy frame for OpenCV diff

        # OCR cadence
        self._ocr_counter = 0
        self._cached_text: list[TextSegment] = []

        # Memory storage
        self._memory = None  # set via configure()

        # Change-detection state (tracks last stored snapshot)
        self._last_stored_ts: float = 0.0
        self._stored_window_title: str = ""
        self._stored_objects_key: str = ""
        self._stored_text_key: str = ""

    # ── Lifecycle ───────────────────────────────────────────────────────────

    def _start(self) -> None:
        if self.running:
            return
        if _mss:
            try:
                self._sct = _mss.mss()
            except Exception as exc:
                logger.warning("mss init failed: %s", exc)
        else:
            logger.warning("mss not installed; VisionSensor will run without screenshots.")
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        logger.info("VisionSensor started (YOLO=%s, OpenCV=%s, EasyOCR=%s)",
                    _YOLO is not None, _cv2 is not None, _easyocr is not None)

    def _stop(self) -> None:
        self.running = False
        if self.thread:
            self.thread.join(timeout=3.0)
        if self._sct:
            self._sct.close()

    # ── Model loading ───────────────────────────────────────────────────────

    def _load_models(self) -> None:
        """Lazy-load YOLO and EasyOCR on first loop iteration."""
        if self._models_loaded:
            return
        self._models_loaded = True  # set before attempting, so failures don't retry

        if _YOLO is not None:
            try:
                self._yolo = _YOLO(YOLO_MODEL)
                logger.info("YOLO model loaded: %s", YOLO_MODEL)
            except Exception as exc:
                logger.warning("YOLO load failed: %s", exc)

        if _easyocr is not None:
            try:
                self._reader = _easyocr.Reader(["en"], gpu=False, verbose=False)
                logger.info("EasyOCR reader initialised")
            except Exception as exc:
                logger.warning("EasyOCR init failed: %s", exc)

    # ── Perception helpers ──────────────────────────────────────────────────

    def _grab_frame(self):
        """Return a numpy HxWx3 BGR frame from the primary monitor, or None."""
        if self._sct is None or _np is None:
            return None
        try:
            monitor = self._sct.monitors[1]
            sct_img = self._sct.grab(monitor)
            return _np.array(sct_img)[:, :, :3]  # drop alpha → BGR
        except Exception as exc:
            logger.debug("Screenshot grab failed: %s", exc)
            return None

    def _detect_objects(self, frame) -> list[VisualObject]:
        """Run YOLO on frame; return top MAX_OBJECTS detections by confidence."""
        if self._yolo is None or frame is None:
            return []
        try:
            results = self._yolo(frame, verbose=False, conf=YOLO_CONFIDENCE)
            objects: list[VisualObject] = []
            for result in results:
                for box in result.boxes:
                    label = result.names[int(box.cls[0])]
                    conf = float(box.conf[0])
                    bbox = [float(v) for v in box.xyxy[0]]
                    objects.append(VisualObject(label=label, confidence=conf, bbox=bbox))
            objects.sort(key=lambda o: o.confidence, reverse=True)
            return objects[:MAX_OBJECTS]
        except Exception as exc:
            logger.debug("YOLO detection error: %s", exc)
            return []

    def _detect_motion(self, frame) -> tuple[bool, list[float] | None]:
        """
        OpenCV frame-difference motion detection.
        Returns (motion_detected, bounding_box_of_largest_region | None).
        """
        if _cv2 is None or _np is None or frame is None:
            return False, None
        try:
            gray = _cv2.cvtColor(frame, _cv2.COLOR_BGR2GRAY)
            gray = _cv2.GaussianBlur(gray, (21, 21), 0)
            if self._prev_frame is None:
                self._prev_frame = gray
                return False, None
            diff = _cv2.absdiff(self._prev_frame, gray)
            self._prev_frame = gray
            _, thresh = _cv2.threshold(diff, 25, 255, _cv2.THRESH_BINARY)
            thresh = _cv2.dilate(thresh, None, iterations=2)
            contours, _ = _cv2.findContours(
                thresh.copy(), _cv2.RETR_EXTERNAL, _cv2.CHAIN_APPROX_SIMPLE
            )
            significant = [c for c in contours if _cv2.contourArea(c) > 5000]
            if significant:
                largest = max(significant, key=_cv2.contourArea)
                x, y, w, h = _cv2.boundingRect(largest)
                return True, [float(x), float(y), float(x + w), float(y + h)]
            return False, None
        except Exception as exc:
            logger.debug("Motion detection error: %s", exc)
            return False, None

    def _detect_text(self, frame) -> list[TextSegment]:
        """
        Run EasyOCR on frame; return up to MAX_TEXT_ITEMS text segments.
        Each segment position is [x_min, y_min, x_max, y_max].
        """
        if self._reader is None or frame is None:
            return []
        try:
            results = self._reader.readtext(frame)
            segments: list[TextSegment] = []
            for (bbox_points, text, conf) in results:
                if conf < OCR_CONFIDENCE or not text.strip():
                    continue
                xs = [float(p[0]) for p in bbox_points]
                ys = [float(p[1]) for p in bbox_points]
                flat_bbox = [min(xs), min(ys), max(xs), max(ys)]
                segments.append(TextSegment(text=text.strip(), position=flat_bbox))
            return segments[:MAX_TEXT_ITEMS]
        except Exception as exc:
            logger.debug("EasyOCR error: %s", exc)
            return []

    def _build_description(
        self,
        title: str,
        objects: list[VisualObject],
        text_segs: list[TextSegment],
        motion: bool,
    ) -> str:
        """
        Build a compact, searchable description string from percept components.
        This string is stored as the Observation content in the graph, so it
        must be useful for keyword and vector retrieval.
        """
        parts: list[str] = []
        if title:
            parts.append(f"Window: \"{title}\"")
        if objects:
            obj_str = ", ".join(
                f"{o.label} ({o.confidence:.2f})" for o in objects[:6]
            )
            if len(objects) > 6:
                obj_str += f" (+{len(objects) - 6} more)"
            parts.append(f"Objects: {obj_str}")
        if text_segs:
            text_labels = [f"\"{t.text}\"" for t in text_segs[:8]]
            if len(text_segs) > 8:
                text_labels.append(f"+{len(text_segs) - 8} more")
            parts.append(f"Text: {', '.join(text_labels)}")
        if motion:
            parts.append("Motion: detected")
        return " | ".join(parts) if parts else "Desktop: no content detected"

    # ── Change detection and memory storage ────────────────────────────────

    def _has_significant_change(
        self,
        title: str,
        objects: list[VisualObject],
        text_segs: list[TextSegment],
        motion: bool,
    ) -> bool:
        """
        Return True if the current percept differs enough from the last stored
        snapshot to warrant writing a new Observation.

        Rules (any one is sufficient):
        - Minimum snapshot interval has elapsed (VISION_MIN_SNAPSHOT_SECONDS)
        - Foreground window title has changed since last store
        - Motion was detected
        - The set of detected object labels has changed since last store
        - More than 3 new text items are visible that weren't in the last store
        """
        now = time.time()
        if now - self._last_stored_ts >= VISION_MIN_SNAPSHOT_SECONDS:
            return True
        if title != self._stored_window_title:
            return True
        if motion:
            return True
        new_obj_key = ",".join(sorted(o.label for o in objects))
        if new_obj_key != self._stored_objects_key:
            return True
        prev_text_set = set(self._stored_text_key.split(",")) if self._stored_text_key else set()
        new_text_set = {t.text for t in text_segs}
        if len(new_text_set - prev_text_set) > 3:
            return True
        return False

    def _maybe_store_observation(
        self,
        percept: VisualPercept,
        title: str,
    ) -> None:
        """
        Store the percept as a Memory observation if a significant change is
        detected. Updates change-detection state only on successful storage.
        """
        if self._memory is None:
            return
        if not self._has_significant_change(
            title, percept.objects, percept.text_in_scene, percept.motion_detected
        ):
            return
        try:
            stored = self._memory.store_visual_observation(percept)
            if stored:
                self._last_stored_ts = percept.timestamp
                self._stored_window_title = title
                self._stored_objects_key = ",".join(sorted(o.label for o in percept.objects))
                self._stored_text_key = ",".join(t.text for t in percept.text_in_scene)
        except Exception as exc:
            logger.debug("Failed to store visual observation: %s", exc)

    # ── Main loop ───────────────────────────────────────────────────────────

    def _loop(self) -> None:
        global _latest_percept

        self._load_models()

        while self.running:
            try:
                # Foreground window title (always available)
                title = ""
                try:
                    hwnd = win32gui.GetForegroundWindow()
                    title = win32gui.GetWindowText(hwnd) if hwnd else ""
                except Exception:
                    pass

                # Screenshot → numpy frame
                frame = self._grab_frame()

                # Object detection (every tick)
                objects = self._detect_objects(frame)

                # Motion detection (every tick; uses internal prev-frame state)
                motion_detected, motion_region = self._detect_motion(frame)

                # OCR (every VISION_OCR_INTERVAL_TICKS ticks)
                self._ocr_counter += 1
                if self._ocr_counter >= VISION_OCR_INTERVAL_TICKS:
                    self._cached_text = self._detect_text(frame)
                    self._ocr_counter = 0
                text_in_scene = self._cached_text

                # Build description
                description = self._build_description(title, objects, text_in_scene, motion_detected)

                percept = VisualPercept(
                    timestamp=time.time(),
                    scene_type="desktop",
                    objects=objects,
                    text_in_scene=text_in_scene,
                    motion_detected=motion_detected,
                    motion_region=motion_region,
                    faces_detected=0,
                    pose_summary="",
                    description=description,
                )

                with _percept_lock:
                    _latest_percept = percept

                self._maybe_store_observation(percept, title)

            except Exception as exc:
                logger.error("VisionSensor loop error: %s", exc)

            time.sleep(VISION_TICK_SECONDS)
```

---

## Part 2 — `coordinators/memory.py`

Add one new public method to the `Memory` class. Place it immediately after the
`store()` method.

```python
def store_visual_observation(
    self,
    percept: "VisualPercept",
    environment: str = "global",
) -> bool:
    """
    Store a VisionSensor percept snapshot as a graph Observation.

    Uses source_type="perceived" to distinguish desktop snapshots from
    conversation exchanges ("observed") and document chunks ("external_content").
    The description field of the percept is used as the Observation content —
    it must be non-empty for storage to proceed.

    Returns True if stored successfully, False otherwise.
    """
    content = str(getattr(percept, "description", "") or "").strip()
    if not content:
        return False
    try:
        self.store(
            content,
            environment=environment,
            source_type="perceived",
        )
        return True
    except Exception:
        return False
```

No other change to `memory.py`.

---

## Part 3 — `coordinators/hands.py`

Add two new action handlers and register them in the dispatch table.

### Handler 1: `get_visible_elements`

Add after `_handle_screenshot`:

```python
def _handle_get_visible_elements(args: dict[str, Any]) -> str:
    """
    Return the currently visible UI labels from the latest VisualPercept as a
    JSON string. Includes EasyOCR text segments and YOLO-detected object labels.
    Used by Reason to know what is on screen before issuing a click_label action.
    """
    import json
    from sensors.vision_sensor import VisionSensor

    percept = VisionSensor.get_latest()
    if not percept:
        return json.dumps({"text_labels": [], "object_labels": []})

    text_labels = [
        {"text": seg.text, "bbox": seg.position}
        for seg in percept.text_in_scene
    ]
    object_labels = [
        {"label": obj.label, "confidence": round(obj.confidence, 3), "bbox": obj.bbox}
        for obj in percept.objects
    ]
    return json.dumps({"text_labels": text_labels, "object_labels": object_labels})
```

### Handler 2: `click_label`

Add after `_handle_get_visible_elements`:

```python
def _handle_click_label(args: dict[str, Any]) -> str:
    """
    Find the first UI element whose visible label contains the given string
    (case-insensitive), then click the center of its bounding box.

    Searches EasyOCR text_in_scene first (highest fidelity for button labels,
    menu items, form fields), then falls back to YOLO object labels.

    Args dict keys:
        label (str): Partial or full text to match. Case-insensitive.
    """
    import pyautogui
    from sensors.vision_sensor import VisionSensor

    label = str(args.get("label", "")).strip().lower()
    if not label:
        return "Error: no label provided for click_label"

    percept = VisionSensor.get_latest()
    if not percept:
        return "Error: no visual percept available — VisionSensor may not be running"

    # Search text_in_scene (EasyOCR) first
    best_bbox: list[float] | None = None
    for seg in percept.text_in_scene:
        if label in seg.text.lower() and len(seg.position) == 4:
            best_bbox = seg.position
            matched_label = seg.text
            break

    # Fall back to YOLO objects if no text match
    if best_bbox is None:
        for obj in percept.objects:
            if label in obj.label.lower() and len(obj.bbox) == 4:
                best_bbox = obj.bbox
                matched_label = obj.label
                break

    if best_bbox is None:
        return (
            f"No element matching \"{label}\" found in current visual percept. "
            f"Use get_visible_elements to see what is currently on screen."
        )

    x = int((best_bbox[0] + best_bbox[2]) / 2)
    y = int((best_bbox[1] + best_bbox[3]) / 2)
    pyautogui.FAILSAFE = False
    pyautogui.click(x, y)
    return f"Clicked \"{matched_label}\" at ({x}, {y})"
```

### Register in the dispatch table

In the `ACTION_HANDLERS` dict at the bottom of `hands.py`, add both entries
alongside the existing screenshot and click entries:

```python
"get_visible_elements": _handle_get_visible_elements,
"click_label": _handle_click_label,
```

### Policy classification

Both new actions must be added to the **greylist** (require approval before
execution) alongside the existing click and type_text actions. Locate the policy
classification constants/dict in `hands.py` and add:

```python
"get_visible_elements": "greylist",
"click_label": "greylist",
```

---

## Part 4 — `coordinators/reason.py`

Update `Reason.process()` to enrich the visual context string passed to
`generate_response()`. The goal: Reason should see not just the prose description
but also a compact list of currently visible labels, so it can decide to call
`click_label` on a named element.

Replace the existing `visual_description` extraction block in `process()`:

```python
visual_description = str(
    (packet.get("visual_percept") or {}).get("description") or ""
).strip()
```

With this expanded block:

```python
_vp = packet.get("visual_percept") or {}
visual_description = str(_vp.get("description") or "").strip()

# For live desktop percepts, append a compact element index so Reason
# can refer to on-screen labels when composing Hands actions.
if _vp.get("scene_type") == "desktop" and visual_description:
    _text_items = _vp.get("text_in_scene") or []
    _obj_items = _vp.get("objects") or []
    _text_labels = [
        t.get("text", "") for t in _text_items[:12]
        if isinstance(t, dict) and t.get("text")
    ]
    _obj_labels = [
        o.get("label", "") for o in _obj_items[:6]
        if isinstance(o, dict) and o.get("label") and o.get("label") not in _text_labels
    ]
    all_labels = _text_labels + _obj_labels
    if all_labels:
        label_list = ", ".join(f'"{lbl}"' for lbl in all_labels[:18])
        visual_description += f"\nVisible elements: {label_list}"
```

No change to `generate_response()` or any other method in `reason.py`.

---

## Tests (`tests/test_vision_realvision.py`)

Create this new test file:

```python
"""Tests for real VisionSensor: YOLO + OpenCV + EasyOCR + memory integration."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from coordinators.percepts import TextSegment, VisualObject, VisualPercept
from sensors.vision_sensor import (
    VisionSensor,
    _build_description_fn,   # see note below
    VISION_MIN_SNAPSHOT_SECONDS,
    VISION_OCR_INTERVAL_TICKS,
    MAX_OBJECTS,
    MAX_TEXT_ITEMS,
    OCR_CONFIDENCE,
)
```

> **Implementation note:** To make `_build_description` and `_has_significant_change`
> testable without instantiating the class, expose them as module-level functions that
> the instance methods delegate to:
>
> ```python
> def _build_description_fn(title, objects, text_segs, motion) -> str:
>     ...  # same logic as the method body
>
> def _has_significant_change_fn(title, objects, text_segs, motion,
>                                 stored_title, stored_obj_key, stored_text_key,
>                                 last_stored_ts) -> bool:
>     ...  # same logic as the method body
> ```
>
> Then the class methods call these functions:
> ```python
> def _build_description(self, title, objects, text_segs, motion):
>     return _build_description_fn(title, objects, text_segs, motion)
> ```
>
> This makes unit testing straightforward without needing a running sensor instance.
> Import `_has_significant_change_fn` in tests the same way.

```python
from sensors.vision_sensor import (
    VisionSensor,
    _build_description_fn,
    _has_significant_change_fn,
    VISION_MIN_SNAPSHOT_SECONDS,
    MAX_OBJECTS,
    MAX_TEXT_ITEMS,
    OCR_CONFIDENCE,
)


# ── _build_description_fn ─────────────────────────────────────────────────────

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
    assert result  # non-empty
    assert "no content" in result.lower()


def test_build_description_caps_objects_display():
    objects = [
        VisualObject(label=f"item{i}", confidence=0.9 - i * 0.01, bbox=[0, 0, 1, 1])
        for i in range(12)
    ]
    result = _build_description_fn("", objects, [], False)
    assert "+6 more" in result  # only first 6 shown with detail


# ── _has_significant_change_fn ────────────────────────────────────────────────

def test_change_triggers_on_min_interval_elapsed():
    """Elapsed time beyond VISION_MIN_SNAPSHOT_SECONDS always triggers."""
    import time
    old_ts = time.time() - VISION_MIN_SNAPSHOT_SECONDS - 1
    assert _has_significant_change_fn("Win", [], [], False,
                                       "Win", "", "", old_ts) is True


def test_change_triggers_on_window_switch():
    import time
    recent = time.time() - 5
    assert _has_significant_change_fn("NewWin", [], [], False,
                                       "OldWin", "", "", recent) is True


def test_change_triggers_on_motion():
    import time
    recent = time.time() - 5
    assert _has_significant_change_fn("Win", [], [], True,
                                       "Win", "", "", recent) is True


def test_no_change_when_identical():
    import time
    recent = time.time() - 5
    objects = [VisualObject(label="cat", confidence=0.9, bbox=[0,0,1,1])]
    text = [TextSegment(text="hello", position=[0,0,1,1])]
    obj_key = "cat"
    text_key = "hello"
    result = _has_significant_change_fn("Win", objects, text, False,
                                         "Win", obj_key, text_key, recent)
    assert result is False


def test_change_triggers_on_new_objects():
    import time
    recent = time.time() - 5
    objects = [VisualObject(label="dog", confidence=0.9, bbox=[0,0,1,1])]
    # prev had "cat", now has "dog"
    assert _has_significant_change_fn("Win", objects, [], False,
                                       "Win", "cat", "", recent) is True


def test_change_triggers_on_many_new_text_items():
    import time
    recent = time.time() - 5
    text_segs = [TextSegment(text=f"item{i}", position=[0,0,1,1]) for i in range(5)]
    # prev text key is empty
    assert _has_significant_change_fn("Win", [], text_segs, False,
                                       "Win", "", "", recent) is True


# ── VisionSensor._detect_objects ─────────────────────────────────────────────

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


# ── VisionSensor._detect_text ────────────────────────────────────────────────

def test_detect_text_returns_empty_without_reader():
    sensor = VisionSensor()
    sensor._reader = None
    result = sensor._detect_text(MagicMock())
    assert result == []


def test_detect_text_filters_low_confidence():
    sensor = VisionSensor()
    sensor._reader = MagicMock(return_value=[
        ([[0,0],[10,0],[10,10],[0,10]], "hello", 0.9),
        ([[0,0],[10,0],[10,10],[0,10]], "noise", 0.1),  # below OCR_CONFIDENCE
    ])
    result = sensor._detect_text(MagicMock())
    texts = [seg.text for seg in result]
    assert "hello" in texts
    assert "noise" not in texts


def test_detect_text_caps_at_max_items():
    sensor = VisionSensor()
    fake_results = [
        ([[0,0],[1,0],[1,1],[0,1]], f"text{i}", 0.9)
        for i in range(MAX_TEXT_ITEMS + 10)
    ]
    sensor._reader = MagicMock(return_value=fake_results)
    result = sensor._detect_text(MagicMock())
    assert len(result) <= MAX_TEXT_ITEMS


# ── VisionSensor._detect_motion ──────────────────────────────────────────────

def test_detect_motion_returns_false_on_first_frame():
    sensor = VisionSensor()
    sensor._prev_frame = None
    # If cv2 not installed, also returns False
    detected, region = sensor._detect_motion(None)
    assert detected is False
    assert region is None


# ── Memory.store_visual_observation ──────────────────────────────────────────

def test_store_visual_observation_calls_store_with_perceived():
    from coordinators.memory import Memory
    memory = Memory()
    memory.store = MagicMock()

    percept = VisualPercept(
        timestamp=1000.0,
        description="Window: \"Notepad\" | Text: \"hello\"",
        scene_type="desktop",
    )
    result = memory.store_visual_observation(percept)

    assert result is True
    memory.store.assert_called_once()
    call_kwargs = memory.store.call_args
    assert call_kwargs.kwargs.get("source_type") == "perceived" or \
           (len(call_kwargs.args) >= 3 and call_kwargs.args[2] == "perceived") or \
           call_kwargs.kwargs.get("source_type") == "perceived"


def test_store_visual_observation_returns_false_for_empty_description():
    from coordinators.memory import Memory
    memory = Memory()
    memory.store = MagicMock()

    percept = VisualPercept(timestamp=1000.0, description="", scene_type="desktop")
    result = memory.store_visual_observation(percept)

    assert result is False
    memory.store.assert_not_called()


# ── Hands: click_label ────────────────────────────────────────────────────────

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
    assert "150" in result  # x center of [100, 200, 200, 230] = 150


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


# ── Hands: get_visible_elements ───────────────────────────────────────────────

def test_get_visible_elements_returns_json():
    import json
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
    import json
    import coordinators.hands as hands_mod

    with patch("coordinators.hands.VisionSensor") as MockVS:
        MockVS.get_latest.return_value = None
        result = hands_mod._handle_get_visible_elements({})

    data = json.loads(result)
    assert data["text_labels"] == []
    assert data["object_labels"] == []


# ── Reason: visual context expansion ─────────────────────────────────────────

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
                "description": "Window: \"Chrome\"",
                "text_in_scene": [{"text": "Submit", "position": [0, 0, 1, 1]}],
                "objects": [],
            },
        }
        reason.process(packet)

    assert captured_system_prompts, "generate_response was not called"
    assert "Submit" in captured_system_prompts[0]
    assert "Visible elements" in captured_system_prompts[0]


def test_reason_does_not_append_elements_for_user_attachment():
    """scene_type='user_attachment' should not get the element label list appended."""
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
```

---

## Verification

```
pytest tests/test_vision_realvision.py -v
pytest tests/test_coordinators.py -v
pytest --ignore=tests/test_graph.py --basetemp .tmp/pytest_vision -v
```

Confirm `world_models/config.py` is not staged:
```
git status
```

Commit:
```
git commit -m "feat: real VisionSensor — YOLO+OpenCV+EasyOCR, memory storage as perceived observations, Hands click_label, Reason element labels"
```

---

## BACKLOG update (do after tests pass)

In `docs/BACKLOG.md`, move **VisionSensor: YOLO + OpenCV** from `⬜` to `✅` and
add the commit hash. Update the test suite baseline count.
