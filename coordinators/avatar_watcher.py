"""
AvatarWatcher — background thread that monitors avatar/assets/incoming/.

When a valid image file appears in the incoming drop zone, AvatarWatcher:
  1. Moves it to avatar/assets/current/ (replacing any prior file of the same name)
  2. Updates the active manifest (avatar/assets/manifest.json)
  3. Broadcasts a swap_texture WebSocket message to the Godot avatar app

The Godot side picks up the absolute path from the message and hot-swaps
its displayed texture without restarting.

This is the Python half of T73. The Godot half (main.gd texture loading)
must be reexported from the Godot editor after updating main.gd.

Wiring: call AvatarWatcher(emit_fn).start() from server.py after the
BrainLoop is initialised. The watcher runs as a daemon thread and stops
when the process exits.
"""

from __future__ import annotations

import json
import logging
import shutil
import threading
import time
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve()
PROJECT_ROOT = _HERE.parents[1]

AVATAR_ASSETS_DIR = PROJECT_ROOT / "avatar" / "assets"
INCOMING_DIR      = AVATAR_ASSETS_DIR / "incoming"
CURRENT_DIR       = AVATAR_ASSETS_DIR / "current"
MANIFEST_PATH     = AVATAR_ASSETS_DIR / "manifest.json"

VALID_EXTENSIONS: frozenset[str] = frozenset({".png", ".jpg", ".jpeg", ".webp"})

POLL_INTERVAL = 2.0   # seconds between scans of the incoming folder


# ---------------------------------------------------------------------------
# AvatarWatcher
# ---------------------------------------------------------------------------

class AvatarWatcher:
    """
    Polls incoming/ every POLL_INTERVAL seconds.  On any new image:
      - moves file to current/
      - updates manifest.json
      - calls self._emit(path_str) so the server can broadcast to Godot
    """

    def __init__(self, emit_fn: Callable[[str], None]):
        """
        emit_fn: callable that takes the absolute path string of the newly
        installed asset and forwards it to the Godot WebSocket clients.
        """
        self._emit = emit_fn
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        _ensure_dirs()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background polling thread (daemon — exits with process)."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="avatar-watcher",
            daemon=True,
        )
        self._thread.start()
        logger.info("AvatarWatcher started, watching %s", INCOMING_DIR)

    def stop(self) -> None:
        """Signal the polling thread to stop (best-effort)."""
        self._stop_event.set()

    def install(self, source: Path) -> str | None:
        """
        Install a specific file directly (bypassing the drop folder).

        Returns the absolute path string of the installed file, or None on
        failure.  Safe to call from any thread.
        """
        return self._install_file(source)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._scan_incoming()
            except Exception:
                logger.exception("AvatarWatcher._scan_incoming error")
            self._stop_event.wait(POLL_INTERVAL)

    def _scan_incoming(self) -> None:
        for path in sorted(INCOMING_DIR.iterdir()):
            if path.suffix.lower() not in VALID_EXTENSIONS:
                continue
            if not path.is_file():
                continue
            installed = self._install_file(path)
            if installed:
                logger.info("AvatarWatcher: installed %s → current/", path.name)
                self._emit(installed)

    def _install_file(self, source: Path) -> str | None:
        """Move source into current/, update manifest, return abs path."""
        try:
            dest = CURRENT_DIR / source.name
            shutil.move(str(source), str(dest))
            _write_manifest(dest)
            return str(dest)
        except Exception:
            logger.exception("AvatarWatcher: failed to install %s", source)
            return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_dirs() -> None:
    INCOMING_DIR.mkdir(parents=True, exist_ok=True)
    CURRENT_DIR.mkdir(parents=True, exist_ok=True)


def _write_manifest(active_path: Path) -> None:
    data = {
        "active": str(active_path),
        "updated_at": time.time(),
    }
    try:
        MANIFEST_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        logger.exception("AvatarWatcher: failed to write manifest")


def read_manifest() -> dict:
    """Return the current manifest, or {} if not yet written."""
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
