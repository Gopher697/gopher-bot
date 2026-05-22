from __future__ import annotations

import threading
import time
import logging

import win32gui
from coordinators.percepts import VisualPercept, TextSegment

try:
    import mss
except ImportError:
    mss = None

logger = logging.getLogger(__name__)

_latest_percept = None
_percept_lock = threading.Lock()

class VisionSensor:
    _instance = None
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.running = False
        self.thread = None
        self.sct = None

    @classmethod
    def start(cls):
        cls.get_instance()._start()

    @classmethod
    def stop(cls):
        cls.get_instance()._stop()

    @classmethod
    def get_latest(cls) -> VisualPercept | None:
        global _latest_percept
        with _percept_lock:
            return _latest_percept

    def _start(self):
        if self.running:
            return
        if not mss:
            logger.warning("mss not installed. VisionSensor will run but produce no captures.")
        else:
            self.sct = mss.mss()
            
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        if self.sct:
            self.sct.close()

    def _loop(self):
        global _latest_percept
        while self.running:
            try:
                if self.sct:
                    monitor = self.sct.monitors[1]
                    _ = self.sct.grab(monitor)
                
                hwnd = win32gui.GetForegroundWindow()
                title = win32gui.GetWindowText(hwnd) if hwnd else ""
                
                percept = VisualPercept(
                    timestamp=time.time(),
                    scene_type="desktop",
                    objects=[],
                    text_in_scene=[TextSegment(text=title, position=[])] if title else [],
                    motion_detected=False
                )
                
                with _percept_lock:
                    _latest_percept = percept
                    
            except Exception as e:
                logger.error(f"VisionSensor loop error: {e}")
                
            time.sleep(0.5)
