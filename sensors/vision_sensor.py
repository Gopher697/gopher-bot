from __future__ import annotations

import logging
import threading
import time

import win32gui
from openai import OpenAI

from coordinators.percepts import TextSegment, VisualObject, VisualPercept

logger = logging.getLogger(__name__)

# -- Optional heavy imports: degrade gracefully without [vision] extras --------

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

# -- Tuning constants ----------------------------------------------------------

VISION_TICK_SECONDS = 2.0
VISION_OCR_INTERVAL_TICKS = 5
VISION_MIN_SNAPSHOT_SECONDS = 60
YOLO_MODEL = "yolov8n.pt"
YOLO_CONFIDENCE = 0.40
MAX_OBJECTS = 10
MAX_TEXT_ITEMS = 20
OCR_CONFIDENCE = 0.50

# -- VLM semantic description (optional) --------------------------------------
# Set VISION_VLM_MODEL to the name of a vision-capable model loaded in LM Studio
# (e.g. "qwen2-vl-7b-instruct") to enable semantic scene descriptions in stored
# memory observations. Leave empty to disable: zero behavior change when unset.
VISION_VLM_MODEL: str = ""
VISION_VLM_BASE_URL: str = "http://localhost:1234/v1"
VISION_VLM_TIMEOUT: int = 30

# -- Module-level state --------------------------------------------------------

_latest_percept: VisualPercept | None = None
_percept_lock = threading.Lock()


def _build_description_fn(
    title: str,
    objects: list[VisualObject],
    text_segs: list[TextSegment],
    motion: bool,
) -> str:
    """
    Build a compact, searchable description string from percept components.
    This string is stored as Observation content in the graph.
    """
    parts: list[str] = []
    if title:
        parts.append(f'Window: "{title}"')
    if objects:
        obj_str = ", ".join(f"{o.label} ({o.confidence:.2f})" for o in objects[:6])
        if len(objects) > 6:
            obj_str += f" (+{len(objects) - 6} more)"
        parts.append(f"Objects: {obj_str}")
    if text_segs:
        text_labels = [f'"{t.text}"' for t in text_segs[:8]]
        if len(text_segs) > 8:
            text_labels.append(f"+{len(text_segs) - 8} more")
        parts.append(f"Text: {', '.join(text_labels)}")
    if motion:
        parts.append("Motion: detected")
    return " | ".join(parts) if parts else "Desktop: no content detected"


def _has_significant_change_fn(
    title: str,
    objects: list[VisualObject],
    text_segs: list[TextSegment],
    motion: bool,
    stored_title: str,
    stored_obj_key: str,
    stored_text_key: str,
    last_stored_ts: float,
) -> bool:
    """
    Return True if the percept differs enough from the last stored snapshot.
    """
    now = time.time()
    if now - last_stored_ts >= VISION_MIN_SNAPSHOT_SECONDS:
        return True
    if title != stored_title:
        return True
    if motion:
        return True
    new_obj_key = ",".join(sorted(o.label for o in objects))
    if new_obj_key != stored_obj_key:
        return True
    prev_text_set = set(stored_text_key.split(",")) if stored_text_key else set()
    new_text_set = {t.text for t in text_segs}
    if len(new_text_set - prev_text_set) > 3:
        return True
    return False


class VisionSensor:
    """
    Singleton background thread that produces VisualPercept snapshots.

    Uses YOLO v8 for object detection, OpenCV for motion detection, and
    EasyOCR for on-screen text recognition. Heavy libraries are optional; if
    absent, each capability degrades to empty output while the foreground
    window-title path continues to function.
    """

    _instance: VisionSensor | None = None

    # -- Singleton interface --------------------------------------------------

    @classmethod
    def get_instance(cls) -> VisionSensor:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def configure(cls, memory=None) -> None:
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

    # -- Construction ---------------------------------------------------------

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
        self._prev_frame = None

        # OCR cadence
        self._ocr_counter = 0
        self._cached_text: list[TextSegment] = []

        # Memory storage
        self._memory = None

        # Change-detection state for last stored snapshot
        self._last_stored_ts: float = 0.0
        self._stored_window_title: str = ""
        self._stored_objects_key: str = ""
        self._stored_text_key: str = ""

    # -- Lifecycle ------------------------------------------------------------

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
        logger.info(
            "VisionSensor started (YOLO=%s, OpenCV=%s, EasyOCR=%s, VLM=%s)",
            _YOLO is not None,
            _cv2 is not None,
            _easyocr is not None,
            bool(VISION_VLM_MODEL),
        )

    def _stop(self) -> None:
        self.running = False
        if self.thread:
            self.thread.join(timeout=3.0)
        if self._sct:
            self._sct.close()

    # -- Model loading --------------------------------------------------------

    def _load_models(self) -> None:
        """Lazy-load YOLO and EasyOCR on first loop iteration."""
        if self._models_loaded:
            return
        self._models_loaded = True

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

    # -- Perception helpers ---------------------------------------------------

    def _grab_frame(self):
        """Return a numpy HxWx3 BGR frame from the primary monitor, or None."""
        if self._sct is None or _np is None:
            return None
        try:
            monitor = self._sct.monitors[1]
            sct_img = self._sct.grab(monitor)
            return _np.array(sct_img)[:, :, :3]
        except Exception as exc:
            logger.debug("Screenshot grab failed: %s", exc)
            return None

    def _grab_png_bytes(self) -> bytes | None:
        """
        Return the primary monitor screenshot as raw PNG bytes, or None on failure.

        This separate capture path is used only for VLM calls and does not
        require numpy.
        """
        if self._sct is None:
            return None
        try:
            import mss.tools

            monitor = self._sct.monitors[1]
            sct_img = self._sct.grab(monitor)
            return mss.tools.to_png(sct_img.rgb, sct_img.size)
        except Exception as exc:
            logger.debug("PNG capture failed: %s", exc)
            return None

    def _describe_with_vlm(self, png_bytes: bytes) -> str:
        """
        Send a desktop screenshot to the configured local VLM.

        Returns a 2-3 sentence semantic screen description, or an empty string
        if the model is not configured, the PNG is empty, or the API call fails.
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
            for bbox_points, text, conf in results:
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
        return _build_description_fn(title, objects, text_segs, motion)

    # -- Change detection and memory storage ---------------------------------

    def _has_significant_change(
        self,
        title: str,
        objects: list[VisualObject],
        text_segs: list[TextSegment],
        motion: bool,
    ) -> bool:
        return _has_significant_change_fn(
            title,
            objects,
            text_segs,
            motion,
            self._stored_window_title,
            self._stored_objects_key,
            self._stored_text_key,
            self._last_stored_ts,
        )

    def _maybe_store_observation(
        self,
        percept: VisualPercept,
        title: str,
    ) -> None:
        """
        Store the percept as a Memory observation if significant change is detected.

        When VISION_VLM_MODEL is set and succeeds, only the stored copy is
        enriched with semantic scene prose. The live percept remains mechanical.
        """
        if self._memory is None:
            return
        if not self._has_significant_change(
            title, percept.objects, percept.text_in_scene, percept.motion_detected
        ):
            return

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

    # -- Main loop ------------------------------------------------------------

    def _loop(self) -> None:
        global _latest_percept

        self._load_models()

        while self.running:
            try:
                title = ""
                try:
                    hwnd = win32gui.GetForegroundWindow()
                    title = win32gui.GetWindowText(hwnd) if hwnd else ""
                except Exception:
                    pass

                frame = self._grab_frame()
                objects = self._detect_objects(frame)
                motion_detected, motion_region = self._detect_motion(frame)

                self._ocr_counter += 1
                if self._ocr_counter >= VISION_OCR_INTERVAL_TICKS:
                    self._cached_text = self._detect_text(frame)
                    self._ocr_counter = 0
                text_in_scene = self._cached_text

                description = self._build_description(
                    title, objects, text_in_scene, motion_detected
                )

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
