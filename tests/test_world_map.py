from __future__ import annotations

import sys
import pytest
from PySide6.QtWidgets import QApplication

from interface.world_map import WorldMapWindow

# Global QApplication instance for headless tests
app = None

def setup_module(module):
    global app
    # Create the application with the offscreen platform plugin
    app = QApplication.instance()
    if not app:
        app = QApplication(["-platform", "offscreen"])

def test_world_map_instantiation():
    """Test that WorldMapWindow instantiates without error."""
    window = WorldMapWindow()
    assert window is not None
    # Cleanup background thread
    window.ws_thread.stop()
    window.ws_thread.wait()

def test_monitor_zones_created():
    """Test that monitor zones are created from QApplication.screens()."""
    window = WorldMapWindow()
    # At least one rect item and one text item per monitor
    # Or len of monitor_items should be > 0 if screens exist.
    if len(app.screens()) > 0:
        assert len(window.monitor_items) > 0
    window.ws_thread.stop()
    window.ws_thread.wait()

def test_persona_payload_parsing():
    """Test that persona payload parsing correctly updates labels."""
    window = WorldMapWindow()
    
    payload = {
        "state": "working",
        "coordinator": "Reason",
        "focus_window": "gopher-bot - Visual Studio Code",
        "neuromodulators": {"da": 0.6, "ne": 0.4, "serotonin": 0.5, "ach": 0.7},
        "timestamp": "2026-05-21T12:00:00Z"
    }
    
    window.on_persona_update(payload)
    
    assert window.lbl_state.text() == "State: working"
    assert window.lbl_coord.text() == "Coordinator: Reason"
    assert window.lbl_focus.text() == "Focus: gopher-bot - Visual Studio Code"
    assert "DA: 0.60" in window.lbl_neuro.text()
    assert "5HT: 0.50" in window.lbl_neuro.text()
    
    window.ws_thread.stop()
    window.ws_thread.wait()
