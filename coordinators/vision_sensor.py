import threading
import time
import logging
from pathlib import Path
from typing import Optional

from interface.reflex import trigger_reflex_alert
from coordinators.percepts import VisualPercept, VisualObject, TextSegment

logger = logging.getLogger("vision_sensor")

MODELS_DIR = Path("D:/Gopher Bot/gopher-bot/models")

# Graceful degradation flags
try:
    import mss
    import numpy as np
    has_mss = True
except ImportError:
    has_mss = False

try:
    import cv2
    has_cv2 = True
except ImportError:
    has_cv2 = False

try:
    from ultralytics import YOLO
    has_yolo = True
except ImportError:
    has_yolo = False

try:
    import easyocr
    has_easyocr = True
except ImportError:
    has_easyocr = False

try:
    import mediapipe as mp
    has_mediapipe = True
except ImportError:
    has_mediapipe = False


class VisionSensor:
    def __init__(self):
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.latest_percept = VisualPercept(timestamp=time.time())
        self._percept_lock = threading.Lock()
        
        self.yolo_model = None
        if has_yolo:
            weights = MODELS_DIR / "yolov8n.pt"
            if weights.exists():
                self.yolo_model = YOLO(str(weights))
                try:
                    import torch
                    dummy = torch.zeros((1, 3, 640, 640))
                    self.yolo_model(dummy, verbose=False)
                except Exception:
                    pass
            else:
                logger.warning(f"YOLO weights missing at {weights}. Run scripts/download_models.py")

        self.ocr_reader = None
        if has_easyocr:
            try:
                self.ocr_reader = easyocr.Reader(['en'], gpu=True)
            except Exception as e:
                logger.warning(f"Failed to init EasyOCR: {e}")

        self.pose_tracker = None
        if has_mediapipe:
            try:
                self.pose_tracker = mp.solutions.pose.Pose(static_image_mode=False)
            except Exception as e:
                logger.warning(f"Failed to init MediaPipe: {e}")

        self.prev_gray = None
        self.motion_threshold = 2000

    def start(self):
        if not has_mss or not has_cv2:
            logger.warning("Missing mss or cv2. VisionSensor will not start.")
            return
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)

    def get_latest_percept(self) -> dict:
        with self._percept_lock:
            return self.latest_percept.to_dict()

    def _loop(self):
        last_heavy_time = 0.0
        
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            
            while self.running:
                loop_start = time.time()
                
                sct_img = sct.grab(monitor)
                frame = np.array(sct_img)
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
                gray = cv2.GaussianBlur(gray, (21, 21), 0)

                motion_detected = False
                motion_region = None
                
                # Motion detection
                if self.prev_gray is not None:
                    delta = cv2.absdiff(self.prev_gray, gray)
                    thresh = cv2.threshold(delta, 25, 255, cv2.THRESH_BINARY)[1]
                    thresh = cv2.dilate(thresh, None, iterations=2)
                    contours, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    
                    for c in contours:
                        if cv2.contourArea(c) > self.motion_threshold:
                            motion_detected = True
                            (x, y, w, h) = cv2.boundingRect(c)
                            motion_region = [x, y, x+w, y+h]
                            break
                            
                    if motion_detected:
                        try:
                            trigger_reflex_alert(coordinator="vision_sensor", focus_window="desktop")
                        except Exception as e:
                            logger.error(f"Reflex trigger error: {e}")

                self.prev_gray = gray
                
                # Fast inference: YOLO (every 500ms alongside loop)
                objects = []
                faces = 0
                if self.yolo_model:
                    try:
                        results = self.yolo_model(frame_bgr, verbose=False)
                        for r in results:
                            for box in r.boxes:
                                cls_id = int(box.cls[0])
                                conf = float(box.conf[0])
                                label = self.yolo_model.names[cls_id]
                                coords = box.xyxy[0].tolist()
                                objects.append(VisualObject(label=label, confidence=conf, bbox=coords))
                                if label == "person":
                                    faces += 1
                    except Exception as e:
                        logger.error(f"YOLO inference error: {e}")

                # Heavy processing: OCR & Pose (every 2.5s)
                text_segments = []
                pose_summary = ""
                
                if loop_start - last_heavy_time > 2.5:
                    last_heavy_time = loop_start
                    
                    if self.ocr_reader:
                        try:
                            small = cv2.resize(frame_bgr, (0, 0), fx=0.5, fy=0.5)
                            ocr_res = self.ocr_reader.readtext(small)
                            for (bbox, text, prob) in ocr_res:
                                if prob > 0.5:
                                    b = [[pt[0]*2, pt[1]*2] for pt in bbox]
                                    flat_b = [b[0][0], b[0][1], b[2][0], b[2][1]]
                                    text_segments.append(TextSegment(text=text, position=flat_b))
                        except Exception as e:
                            logger.error(f"EasyOCR error: {e}")
                                
                    if self.pose_tracker:
                        try:
                            pose_results = self.pose_tracker.process(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
                            if pose_results.pose_landmarks:
                                pose_summary = "Person detected with pose landmarks"
                        except Exception as e:
                            logger.error(f"MediaPipe error: {e}")

                percept = VisualPercept(
                    timestamp=loop_start,
                    objects=objects,
                    motion_detected=motion_detected,
                    motion_region=motion_region,
                    scene_type="desktop",
                    text_in_scene=text_segments,
                    faces_detected=faces,
                    pose_summary=pose_summary
                )
                
                with self._percept_lock:
                    if loop_start - last_heavy_time <= 2.5 and not text_segments:
                        percept.text_in_scene = self.latest_percept.text_in_scene
                        percept.pose_summary = self.latest_percept.pose_summary
                    
                    self.latest_percept = percept

                # Target 500ms per loop ~ 2fps
                elapsed = time.time() - loop_start
                sleep_time = max(0, 0.5 - elapsed)
                time.sleep(sleep_time)
