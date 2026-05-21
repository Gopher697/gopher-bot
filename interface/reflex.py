from typing import Callable, Optional

_reflex_handler: Optional[Callable[[str, str], None]] = None

def register_reflex_handler(handler: Callable[[str, str], None]) -> None:
    global _reflex_handler
    _reflex_handler = handler

def trigger_reflex_alert(coordinator: str = "sensory", focus_window: str = "") -> None:
    if _reflex_handler:
        _reflex_handler(coordinator, focus_window)
