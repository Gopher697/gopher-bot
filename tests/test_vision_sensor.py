from __future__ import annotations

import time
from unittest.mock import patch
from sensors.vision_sensor import VisionSensor
from coordinators.percepts import VisualPercept

def test_vision_sensor_get_latest():
    sensor = VisionSensor()
    # Before start, it should be None
    assert sensor.get_latest() is None
    
    # Mock win32gui to simulate a window
    with patch("sensors.vision_sensor.win32gui.GetForegroundWindow") as mock_get_hwnd, \
         patch("sensors.vision_sensor.win32gui.GetWindowText") as mock_get_text, \
         patch("sensors.vision_sensor.mss") as mock_mss:
         
        mock_get_hwnd.return_value = 12345
        mock_get_text.return_value = "Test Window"
        
        sensor._start()
        
        # Wait for loop to run at least once
        time.sleep(0.6)
        
        latest = sensor.get_latest()
        assert latest is not None
        assert isinstance(latest, VisualPercept)
        assert latest.scene_type == "desktop"
        assert len(latest.text_in_scene) == 1
        assert latest.text_in_scene[0].text == "Test Window"
        
        sensor._stop()
