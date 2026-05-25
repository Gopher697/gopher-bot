"""
Hands — motor cortex coordinator.

The only coordinator that takes real-world actions (file I/O, subprocesses,
network). Every action passes through the policy interception layer before
executing. Every file-modifying action is snapshotted for rollback on error.

Integration point in the Awareness pipeline:
    reason.process(packet) → hands.process(packet) → voice.process(packet)

Hands only acts when the packet contains an "action" key (placed there by
Reason). If no action is present, process() returns the packet unchanged.

Action log: logs/actions/hands_actions.jsonl
  Every action attempt — executed, blocked, or pending — is logged here.
  Required by Charter Article VI for any action that modifies files.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from coordinators.base import PROJECT_ROOT, Coordinator
from coordinators.bid import PRIORITY_HANDS, BidQueue
from coordinators.hands_policy import PolicyDecision, classify_action
from utils.audit_log import AuditLog

try:
    import pyautogui
except ImportError:
    pyautogui = None

from sensors.vision_sensor import VisionSensor


HANDS_ACTION_LOG_PATH = PROJECT_ROOT / "logs" / "actions" / "hands_actions.jsonl"
HANDS_AUDIT_LOG_PATH = PROJECT_ROOT / "logs" / "audit" / "hands_audit.jsonl"
HANDS_SNAPSHOT_DIR = PROJECT_ROOT / "logs" / "actions" / ".snapshots"


ActionLogWriter = Callable[[dict[str, Any]], None]
SnapshotFn = Callable[[Path], bytes | None]
RestoreFn = Callable[[Path, bytes], None]


class Hands(Coordinator):
    """
    Motor cortex — executes approved actions in the real world.

    All action types flow through classify_action() first. Results:
      whitelist  → execute immediately, log, return result in packet
      greylist   → log as "pending_approval", submit bid to Awareness, do not execute
      blacklist  → log as "blocked", submit alert bid if bid_queue available, do not execute
    """

    name = "hands"

    def __init__(
        self,
        action_log_writer: ActionLogWriter | None = None,
        snapshot_fn: SnapshotFn | None = None,
        restore_fn: RestoreFn | None = None,
        time_fn: Callable[[], float] = time.time,
        bid_queue: BidQueue | None = None,
    ) -> None:
        self.action_log_writer = action_log_writer
        self._audit_log = AuditLog(HANDS_AUDIT_LOG_PATH)
        self.snapshot_fn = snapshot_fn or _read_file_bytes
        self.restore_fn = restore_fn or _write_file_bytes
        self.time_fn = time_fn
        self.bid_queue = bid_queue

    # ------------------------------------------------------------------
    # Coordinator interface
    # ------------------------------------------------------------------

    def process(self, packet: dict[str, Any]) -> dict[str, Any]:
        """
        Execute an action if the packet contains one.

        Reads ``packet["action"]`` — a dict with at minimum:
            {"type": "<action_type>", "args": {...}}

        Writes ``packet["action_result"]`` with the outcome and returns the
        modified packet. If no action is present, returns packet unchanged.
        """
        action = packet.get("action")
        if not action:
            return packet

        action_type = str(action.get("type") or "").strip()
        args: dict[str, Any] = dict(action.get("args") or {})

        decision = classify_action(action_type, args)
        result = self._dispatch(decision, args)

        self._log_action(action_type, args, decision, result)

        if result.get("status") in ("blocked", "pending_approval"):
            self._submit_bid(decision, result)

        packet["action_result"] = result
        return packet

    async def background_tick(self, bid_queue: BidQueue) -> None:
        """
        Background heartbeat — no-op in the basic framework.

        Future: check pending greylist queue for stale approvals.
        """
        return

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def _dispatch(
        self,
        decision: PolicyDecision,
        args: dict[str, Any],
    ) -> dict[str, Any]:
        if decision.policy_class == "blacklist":
            return {
                "status": "blocked",
                "policy_class": "blacklist",
                "reason": decision.reason,
            }

        if decision.policy_class == "greylist":
            return {
                "status": "pending_approval",
                "policy_class": "greylist",
                "reason": decision.reason,
            }

        # whitelist — execute
        handler = _WHITELIST_HANDLERS.get(decision.action_type)
        if handler is None:
            return {
                "status": "executed",
                "policy_class": "whitelist",
                "output": None,
                "note": f"no handler registered for {decision.action_type!r}",
            }

        snapshot: bytes | None = None
        affected_path: Path | None = _affected_path(args)
        if affected_path is not None and _is_write_action(decision.action_type):
            snapshot = self.snapshot_fn(affected_path)

        try:
            output = handler(args)
        except Exception as exc:
            if snapshot is not None and affected_path is not None:
                try:
                    self.restore_fn(affected_path, snapshot)
                except Exception:
                    pass
            return {
                "status": "error",
                "policy_class": "whitelist",
                "error": str(exc),
            }

        return {
            "status": "executed",
            "policy_class": "whitelist",
            "output": output,
        }

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log_action(
        self,
        action_type: str,
        args: dict[str, Any],
        decision: PolicyDecision,
        result: dict[str, Any],
    ) -> None:
        entry = {
            "timestamp": self.time_fn(),
            "action_type": action_type,
            "policy_class": decision.policy_class,
            "status": result.get("status"),
            "reason": decision.reason,
            "path": decision.path,
            "args_summary": _sanitise_args(args),
        }
        try:
            if self.action_log_writer is not None:
                self.action_log_writer(entry)
            else:
                event_type = str(entry.get("policy_class") or "hands_action")
                data = {
                    key: value
                    for key, value in entry.items()
                    if key != "policy_class"
                }
                data = json.loads(json.dumps(data, default=str))
                self._audit_log.append(event_type, data)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Bid submission
    # ------------------------------------------------------------------

    def _submit_bid(
        self,
        decision: PolicyDecision,
        result: dict[str, Any],
    ) -> None:
        if self.bid_queue is None:
            return
        from coordinators.bid import Bid

        status = result.get("status", "")
        if status == "blocked":
            content = (
                f"Hands blocked action {decision.action_type!r}: {decision.reason}"
            )
        else:
            content = (
                f"Hands action {decision.action_type!r} pending approval: "
                f"{decision.reason}"
            )
        try:
            self.bid_queue.submit(
                Bid(
                    coordinator_name=self.name,
                    content=content,
                    priority=PRIORITY_HANDS,
                    timestamp=self.time_fn(),
                )
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Whitelist action handlers
# ---------------------------------------------------------------------------

def _handle_read_file(args: dict[str, Any]) -> str:
    path = Path(str(args["path"]))
    return path.read_text(encoding="utf-8", errors="replace")


def _handle_list_directory(args: dict[str, Any]) -> list[str]:
    path = Path(str(args["path"]))
    return [entry.name for entry in sorted(path.iterdir())]


def _handle_search_notes(args: dict[str, Any]) -> str:
    # Stub — real implementation connects to the workbench MCP in a future task.
    query = str(args.get("query") or "")
    return f"[search_notes stub: query={query!r} — not yet implemented]"


def _handle_search_web(args: dict[str, Any]) -> str:
    # Stub — real implementation adds a web search tool in a future task.
    query = str(args.get("query") or "")
    return f"[search_web stub: query={query!r} — not yet implemented]"


def _handle_append_note(args: dict[str, Any]) -> str:
    path = Path(str(args["path"]))
    content = str(args.get("content") or "")
    # Safety: append-only, designated notes paths only.
    # Policy layer already cleared this path; just execute.
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(content)
    return f"appended {len(content)} chars to {path}"


def _handle_screenshot(args: dict[str, Any]) -> str:
    import mss
    import mss.tools
    import base64
    import os
    import tempfile
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        sct_img = sct.grab(monitor)
        fd, path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            mss.tools.to_png(sct_img.rgb, sct_img.size, output=path)
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")
        finally:
            os.remove(path)
        return b64


def _handle_get_visible_elements(args: dict[str, Any]) -> str:
    """
    Return visible UI labels from the latest VisualPercept as JSON.
    Includes EasyOCR text segments and YOLO-detected object labels.
    """
    percept = VisionSensor.get_latest()
    if not percept:
        return json.dumps({"text_labels": [], "object_labels": []})

    text_labels = [
        {"text": seg.text, "bbox": seg.position}
        for seg in percept.text_in_scene
    ]
    object_labels = [
        {
            "label": obj.label,
            "confidence": round(obj.confidence, 3),
            "bbox": obj.bbox,
        }
        for obj in percept.objects
    ]
    return json.dumps({"text_labels": text_labels, "object_labels": object_labels})


def _handle_click_label(args: dict[str, Any]) -> str:
    """
    Click the first visible element whose label contains the requested string.
    EasyOCR text matches are preferred over YOLO object-label matches.
    """
    label = str(args.get("label", "")).strip().lower()
    if not label:
        return "Error: no label provided for click_label"

    percept = VisionSensor.get_latest()
    if not percept:
        return "Error: no visual percept available — VisionSensor may not be running"

    best_bbox: list[float] | None = None
    matched_label = ""
    for seg in percept.text_in_scene:
        if label in seg.text.lower() and len(seg.position) == 4:
            best_bbox = seg.position
            matched_label = seg.text
            break

    if best_bbox is None:
        for obj in percept.objects:
            if label in obj.label.lower() and len(obj.bbox) == 4:
                best_bbox = obj.bbox
                matched_label = obj.label
                break

    if best_bbox is None:
        return (
            f'No element matching "{label}" found in current visual percept. '
            "Use get_visible_elements to see what is currently on screen."
        )

    if pyautogui is None:
        return "Error: pyautogui not installed; click_label cannot execute"

    x = int((best_bbox[0] + best_bbox[2]) / 2)
    y = int((best_bbox[1] + best_bbox[3]) / 2)
    pyautogui.FAILSAFE = False
    pyautogui.click(x, y)
    return f'Clicked "{matched_label}" at ({x}, {y})'


def _handle_mouse_move(args: dict[str, Any]) -> str:
    import pyautogui
    pyautogui.FAILSAFE = False
    x, y = int(args.get("x", 0)), int(args.get("y", 0))
    pyautogui.moveTo(x, y)
    return f"Moved mouse to ({x}, {y})"


def _handle_left_click(args: dict[str, Any]) -> str:
    import pyautogui
    pyautogui.FAILSAFE = False
    x, y = args.get("x"), args.get("y")
    if x is not None and y is not None:
        pyautogui.click(int(x), int(y))
        return f"Left clicked at ({x}, {y})"
    pyautogui.click()
    return "Left clicked at current position"


def _handle_right_click(args: dict[str, Any]) -> str:
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.rightClick()
    return "Right clicked at current position"


def _handle_double_click(args: dict[str, Any]) -> str:
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.doubleClick()
    return "Double clicked at current position"


def _handle_type_text(args: dict[str, Any]) -> str:
    import pyautogui
    text = args.get("text", "")
    pyautogui.write(text)
    return f"Typed {len(text)} characters"


def _handle_key_press(args: dict[str, Any]) -> str:
    import pyautogui
    key = args.get("key", "")
    pyautogui.press(key)
    return f"Pressed key: {key}"


def _handle_get_window_list(args: dict[str, Any]) -> list[str]:
    import pywinauto
    desktop = pywinauto.Desktop(backend="uia")
    return [w.window_text() for w in desktop.windows() if w.window_text()]


def _handle_focus_window(args: dict[str, Any]) -> str:
    import pywinauto
    title = args.get("title", "")
    desktop = pywinauto.Desktop(backend="uia")
    window = desktop.window(title_re=f".*{title}.*")
    window.set_focus()
    return f"Focused window matching: {title}"


def _handle_click_element(args: dict[str, Any]) -> str:
    import pywinauto
    title = args.get("title", "")
    control_type = args.get("control_type", "")
    element_title = args.get("element_title", "")
    desktop = pywinauto.Desktop(backend="uia")
    window = desktop.window(title_re=f".*{title}.*")
    
    kwargs = {}
    if element_title:
        kwargs["title_re"] = f".*{element_title}.*"
    if control_type:
        kwargs["control_type"] = control_type
        
    element = window.child_window(**kwargs)
    element.click_input()
    return f"Clicked element matching {element_title} in window {title}"


def _handle_click_bbox(args: dict[str, Any]) -> str:
    import pyautogui
    pyautogui.FAILSAFE = False
    bbox = args.get("bbox", [])
    if isinstance(bbox, list) and len(bbox) == 4:
        x = int((bbox[0] + bbox[2]) / 2)
        y = int((bbox[1] + bbox[3]) / 2)
        pyautogui.click(x, y)
        return f"Clicked bbox center at ({x}, {y})"
    return "Invalid bbox"


def _handle_swap_avatar_sprite(args: dict[str, Any]) -> str:
    """
    Install an asset file into avatar/assets/current/ and queue it for
    broadcast to the running Godot avatar app via the AvatarWatcher drop zone.

    args:
      source_path (str) — absolute or project-relative path to the source image.
                          Must be .png / .jpg / .jpeg / .webp.
    """
    import shutil
    from pathlib import Path
    from coordinators.avatar_watcher import INCOMING_DIR, VALID_EXTENSIONS

    raw_path = args.get("source_path") or args.get("path") or ""
    source = Path(str(raw_path))
    if not source.is_absolute():
        source = PROJECT_ROOT / source
    if not source.exists():
        return f"swap_avatar_sprite: source not found: {source}"
    if source.suffix.lower() not in VALID_EXTENSIONS:
        return f"swap_avatar_sprite: unsupported format {source.suffix!r} (use png/jpg/webp)"

    dest = INCOMING_DIR / source.name
    shutil.copy2(str(source), str(dest))
    return f"swap_avatar_sprite: queued {source.name} -> incoming/ (watcher will install + broadcast)"

_WHITELIST_HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "read_file": _handle_read_file,
    "list_directory": _handle_list_directory,
    "search_notes": _handle_search_notes,
    "search_web": _handle_search_web,
    "append_note": _handle_append_note,
    "screenshot": _handle_screenshot,
    "get_visible_elements": _handle_get_visible_elements,
    "click_label": _handle_click_label,
    "mouse_move": _handle_mouse_move,
    "left_click": _handle_left_click,
    "right_click": _handle_right_click,
    "double_click": _handle_double_click,
    "type_text": _handle_type_text,
    "key_press": _handle_key_press,
    "get_window_list": _handle_get_window_list,
    "focus_window": _handle_focus_window,
    "click_element": _handle_click_element,
    "click_bbox": _handle_click_bbox,
    "swap_avatar_sprite": _handle_swap_avatar_sprite,
}


# ---------------------------------------------------------------------------
# Snapshot / restore helpers
# ---------------------------------------------------------------------------

def _is_write_action(action_type: str) -> bool:
    return action_type in {"append_note", "write_file"}


def _affected_path(args: dict[str, Any]) -> Path | None:
    raw = args.get("path") or args.get("file_path")
    if raw is None:
        return None
    return Path(str(raw))


def _read_file_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except (FileNotFoundError, PermissionError):
        return None


def _write_file_bytes(path: Path, data: bytes) -> None:
    path.write_bytes(data)


# ---------------------------------------------------------------------------
# Log helpers
# ---------------------------------------------------------------------------

def _append_action_log(
    entry: dict[str, Any],
    path: Path = HANDS_ACTION_LOG_PATH,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True, default=str) + "\n")


def _sanitise_args(args: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of args safe to log — truncate long values."""
    out = {}
    for key, value in args.items():
        if isinstance(value, str) and len(value) > 200:
            out[key] = value[:200] + "…"
        else:
            out[key] = value
    return out
