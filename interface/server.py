from __future__ import annotations

import base64
import asyncio
import itertools
import subprocess
import sys
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request, send_from_directory
from flask_socketio import SocketIO, emit


ROOT = Path(__file__).resolve().parents[1]
INTERFACE_DIR = Path(__file__).resolve().parent
STARTUP_SCRIPT = ROOT / "scripts" / "startup.py"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(INTERFACE_DIR) not in sys.path:
    sys.path.insert(0, str(INTERFACE_DIR))

from coordinators.base import read_coordinator_log_entries  # noqa: E402
from coordinators.brain_loop import BrainLoop  # noqa: E402
from interface import bot, stt, tts  # noqa: E402


app = Flask(__name__, static_folder="static", static_url_path="")
socketio = SocketIO(app, cors_allowed_origins="*")
_proactive_messages: list[dict[str, object]] = []
_proactive_message_lock = threading.Lock()
_next_proactive_message_id = itertools.count(1)


AUDIT_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Coordinator Activity</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0d0f12;
      --panel: #161a20;
      --panel-strong: #1e2530;
      --ink: #e2e8f0;
      --muted: #94a3b8;
      --line: #2a303c;
      --accent: #246bfe;
      --accent-dark: #174fc5;
      --ok: #22c55e;
      --warn: #f59e0b;
      --danger: #ef4444;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--ink);
      padding: 24px;
    }

    main {
      width: min(1120px, 100%);
      margin: 0 auto;
      display: grid;
      gap: 16px;
    }

    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }

    h1,
    h2 {
      margin: 0;
      line-height: 1.2;
    }

    h1 {
      font-size: 24px;
      font-weight: 700;
    }

    h2 {
      font-size: 16px;
      font-weight: 700;
    }

    button {
      border: 0;
      border-radius: 6px;
      padding: 10px 14px;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
      color: white;
      background: var(--accent);
    }

    button:hover {
      background: var(--accent-dark);
    }

    .status-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(120px, 1fr));
      gap: 12px;
    }

    .meter {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      min-height: 84px;
    }

    .meter-label {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
    }

    .meter-value {
      margin-top: 10px;
      font-size: 26px;
      font-variant-numeric: tabular-nums;
      font-weight: 700;
    }

    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }

    .panel-heading {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      background: var(--panel-strong);
    }

    #connection-status {
      color: var(--muted);
      font-size: 13px;
    }

    .table-wrap {
      overflow-x: auto;
    }

    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 840px;
    }

    th,
    td {
      padding: 12px 14px;
      text-align: left;
      border-bottom: 1px solid var(--line);
      font-size: 14px;
      white-space: nowrap;
    }

    th {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
    }

    td {
      font-variant-numeric: tabular-nums;
    }

    .empty {
      color: var(--muted);
      text-align: center;
      padding: 28px 14px;
    }

    .accepted {
      color: var(--ok);
      font-weight: 700;
    }

    .rejected {
      color: var(--danger);
      font-weight: 700;
    }

    .pending {
      color: var(--warn);
      font-weight: 700;
    }

    @media (max-width: 720px) {
      body {
        padding: 12px;
      }

      header,
      .panel-heading {
        align-items: flex-start;
        flex-direction: column;
      }

      .status-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <h1>Coordinator Activity</h1>
      <button id="feed-toggle" type="button">Pause</button>
    </header>

    <section aria-labelledby="brain-status-heading">
      <div class="panel-heading">
        <h2 id="brain-status-heading">Brain Status</h2>
        <div id="status-timestamp">Waiting for status</div>
      </div>
      <div class="status-grid" aria-live="polite">
        <div class="meter">
          <div class="meter-label">DA</div>
          <div class="meter-value" id="level-da">--</div>
        </div>
        <div class="meter">
          <div class="meter-label">NE</div>
          <div class="meter-value" id="level-ne">--</div>
        </div>
        <div class="meter">
          <div class="meter-label">5HT</div>
          <div class="meter-value" id="level-5ht">--</div>
        </div>
        <div class="meter">
          <div class="meter-label">ACh</div>
          <div class="meter-value" id="level-ach">--</div>
        </div>
      </div>
    </section>

    <section class="panel" aria-labelledby="activity-heading">
      <div class="panel-heading">
        <h2 id="activity-heading">Live Feed</h2>
        <div id="connection-status">Connecting</div>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Coordinator</th>
              <th>Event</th>
              <th>Confidence</th>
              <th>Tier</th>
              <th>Cost</th>
              <th>Accepted</th>
            </tr>
          </thead>
          <tbody id="audit-body">
            <tr id="empty-row">
              <td class="empty" colspan="7">Waiting for coordinator ticks</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </main>

  <script src="/socket.io/socket.io.js"></script>
  <script>
    const auditBody = document.getElementById("audit-body");
    const emptyRow = document.getElementById("empty-row");
    const toggleButton = document.getElementById("feed-toggle");
    const connectionStatus = document.getElementById("connection-status");
    const statusTimestamp = document.getElementById("status-timestamp");
    const levelEls = {
      DA: document.getElementById("level-da"),
      NE: document.getElementById("level-ne"),
      "5HT": document.getElementById("level-5ht"),
      ACh: document.getElementById("level-ach")
    };
    let paused = false;
    const seenAuditKeys = new Set();

    function text(value, fallback = "--") {
      if (value === null || value === undefined || value === "") {
        return fallback;
      }
      return String(value);
    }

    function formatTime(timestamp) {
      const numeric = Number(timestamp);
      if (!Number.isFinite(numeric)) {
        return "--";
      }
      return new Date(numeric * 1000).toLocaleTimeString();
    }

    function formatPercent(value) {
      const numeric = Number(value);
      if (!Number.isFinite(numeric)) {
        return "--";
      }
      return `${Math.round(numeric * 100)}%`;
    }

    function formatCost(value) {
      const numeric = Number(value);
      if (!Number.isFinite(numeric)) {
        return "--";
      }
      return `$${numeric.toFixed(5)}`;
    }

    function acceptedCell(value) {
      if (value === true) {
        return { label: "Yes", className: "accepted" };
      }
      if (value === false) {
        return { label: "No", className: "rejected" };
      }
      return { label: "Pending", className: "pending" };
    }

    function auditKey(entry) {
      return [
        text(entry.timestamp),
        text(entry.coordinator),
        text(entry.event),
        text(entry.accepted)
      ].join("|");
    }

    function addAuditRow(entry) {
      if (paused) {
        return;
      }
      const key = auditKey(entry);
      if (seenAuditKeys.has(key)) {
        return;
      }
      seenAuditKeys.add(key);

      if (emptyRow) {
        emptyRow.remove();
      }

      const row = document.createElement("tr");
      const accepted = acceptedCell(entry.accepted);
      const values = [
        formatTime(entry.timestamp),
        text(entry.coordinator),
        text(entry.event),
        formatPercent(entry.confidence),
        text(entry.tier_used),
        formatCost(entry.actual_cost_usd),
        accepted.label
      ];

      values.forEach((value, index) => {
        const cell = document.createElement("td");
        cell.textContent = value;
        if (index === 6) {
          cell.className = accepted.className;
        }
        row.appendChild(cell);
      });

      auditBody.prepend(row);
      while (auditBody.children.length > 100) {
        auditBody.lastElementChild.remove();
      }
    }

    async function refreshAuditLog() {
      try {
        const response = await fetch("/audit-log?limit=50");
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error || "audit log request failed");
        }
        (payload.entries || []).forEach(addAuditRow);
      } catch (error) {
        if (!window.io) {
          connectionStatus.textContent = "Polling unavailable";
        }
      }
    }

    async function refreshBrainStatus() {
      try {
        const response = await fetch("/brain-status");
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error || "status request failed");
        }

        const levels = payload.neuromodulators || {};
        Object.entries(levelEls).forEach(([channel, element]) => {
          element.textContent = formatPercent(levels[channel]);
        });
        statusTimestamp.textContent = payload.running ? "Running" : "Idle";
      } catch (error) {
        statusTimestamp.textContent = "Status unavailable";
      }
    }

    toggleButton.addEventListener("click", () => {
      paused = !paused;
      toggleButton.textContent = paused ? "Resume" : "Pause";
      connectionStatus.textContent = paused ? "Feed paused" : "Feed live";
    });

    if (window.io) {
      const socket = io({ transports: ["websocket", "polling"] });
      socket.on("connect", () => {
        connectionStatus.textContent = paused ? "Feed paused" : "Feed live";
      });
      socket.on("disconnect", () => {
        connectionStatus.textContent = "Disconnected";
      });
      socket.on("connect_error", () => {
        connectionStatus.textContent = "Polling every 5s";
      });
      socket.on("audit_update", addAuditRow);
    } else {
      connectionStatus.textContent = "Polling every 5s";
    }

    refreshBrainStatus();
    refreshAuditLog();
    window.setInterval(refreshBrainStatus, 5000);
    window.setInterval(refreshAuditLog, 5000);
  </script>
</body>
</html>
"""


def _emit_audit_update(payload: dict) -> None:
    socketio.emit("audit_update", payload)


def _emit_proactive_response(text: str) -> None:
    message = {"id": next(_next_proactive_message_id), "text": text}
    with _proactive_message_lock:
        _proactive_messages.append(message)
        del _proactive_messages[:-100]
    socketio.emit("response", message)


def _emit_persona_state(state: str, coordinator: str = "", focus_window: str = "") -> None:
    now = time.time()
    neuromods = _neuromodulator_levels(brain_loop)
    
    mapped_neuromods = {
        "da": neuromods.get("DA", 0.0),
        "ne": neuromods.get("NE", 0.0),
        "serotonin": neuromods.get("5HT", 0.0),
        "ach": neuromods.get("ACh", 0.0)
    }
    
    payload = {
        "state": state,
        "coordinator": coordinator,
        "focus_window": focus_window,
        "neuromodulators": mapped_neuromods,
        "timestamp": now
    }
    socketio.emit("state_update", payload, namespace="/persona")


def _emit_persona_alert(coordinator: str = "sensory", focus_window: str = "") -> None:
    """Registered as the global reflex handler."""
    brain_loop.interrupt_event.set()
    _emit_persona_state("alert", coordinator=coordinator, focus_window=focus_window)


brain_loop = BrainLoop(
    audit_event_emitter=_emit_audit_update,
    proactive_response_emitter=_emit_proactive_response,
)
_brain_thread: threading.Thread | None = None
_brain_thread_lock = threading.Lock()


def run_startup_script() -> None:
    completed = subprocess.run(
        [sys.executable, str(STARTUP_SCRIPT)],
        cwd=ROOT,
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    if completed.returncode != 0:
        print(
            f"startup.py exited with status {completed.returncode}",
            file=sys.stderr,
        )


def start_brain_loop() -> BrainLoop:
    global _brain_thread
    with _brain_thread_lock:
        if _brain_thread is not None and _brain_thread.is_alive():
            return brain_loop

        _brain_thread = threading.Thread(
            target=_run_brain_loop_thread,
            name="gopher-brain-loop",
            daemon=True,
        )
        _brain_thread.start()
        return brain_loop


def stop_brain_loop() -> None:
    brain_loop.stop()


def _run_brain_loop_thread() -> None:
    try:
        asyncio.run(brain_loop.start(bot.awareness))
    except Exception:
        app.logger.exception("Brain loop stopped unexpectedly")


def _message_from_json() -> tuple[str | None, tuple | None]:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return None, (jsonify({"error": "Expected JSON object"}), 400)

    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        return None, (jsonify({"error": "message must be a non-empty string"}), 400)

    return message.strip(), None


def _process_message(message: str) -> str:
    packet = bot.awareness.synchronous_run(message)
    return bot.response_from_packet(packet)


def _neuromodulator_levels(loop: BrainLoop) -> dict[str, float]:
    neuromodulation = getattr(loop, "coordinators", {}).get("neuromodulation")
    state = getattr(neuromodulation, "state", None)
    channels = getattr(state, "channels", None)
    if not isinstance(channels, dict):
        return {}

    levels: dict[str, float] = {}
    for name in ("DA", "NE", "5HT", "ACh"):
        channel = channels.get(name)
        if channel is None:
            continue
        tonic = _safe_float(getattr(channel, "tonic", 0.0), 0.0)
        phasic = _safe_float(getattr(channel, "phasic", 0.0), 0.0)
        levels[name] = max(0.0, min(1.0, tonic + phasic))
    return levels


def _safe_float(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _audit_payload_from_log_entry(entry: dict) -> dict:
    return {
        "timestamp": entry.get("timestamp"),
        "coordinator": entry.get("coordinator_name"),
        "event": entry.get("event"),
        "confidence": entry.get("confidence"),
        "tier_used": entry.get("tier_used"),
        "actual_cost_usd": entry.get("actual_cost_usd"),
        "accepted": entry.get("accepted"),
    }


def _unread_proactive_messages(since: int) -> list[dict[str, object]]:
    with _proactive_message_lock:
        return [
            dict(message)
            for message in _proactive_messages
            if _safe_int(message.get("id"), 0) > since
        ]


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/audit")
def audit():
    return render_template_string(AUDIT_TEMPLATE)


@app.get("/audit-log")
def audit_log():
    limit = max(1, min(100, _safe_int(request.args.get("limit"), 50)))
    return jsonify(
        {
            "entries": [
                _audit_payload_from_log_entry(entry)
                for entry in read_coordinator_log_entries(limit)
            ]
        }
    )


@app.get("/proactive-messages")
def proactive_messages():
    since = max(0, _safe_int(request.args.get("since"), 0))
    return jsonify({"messages": _unread_proactive_messages(since)})


@app.post("/chat")
def chat():
    message, error = _message_from_json()
    if error is not None:
        return error

    try:
        response = _process_message(message)
    except Exception:
        app.logger.exception("Chat request failed")
        return jsonify({"error": "Chat request failed"}), 500

    return jsonify({"response": response})


@app.get("/brain-status")
def brain_status():
    return jsonify(
        {
            "running": bool(brain_loop.running),
            "last_ticks": dict(brain_loop.last_ticks),
            "pending_bids": bot.awareness.bid_queue.qsize(),
            "neuromodulators": _neuromodulator_levels(brain_loop),
        }
    )


@app.post("/voice")
def voice():
    audio_bytes = request.get_data(cache=False)
    if not audio_bytes:
        return jsonify({"error": "Expected raw audio bytes"}), 400

    try:
        transcript = stt.transcribe(audio_bytes)
        response = _process_message(transcript)
        audio = tts.speak(response)
    except Exception:
        app.logger.exception("Voice request failed")
        return jsonify({"error": "Voice request failed"}), 500

    return jsonify(
        {
            "transcript": transcript,
            "response": response,
            "audio": base64.b64encode(audio).decode("ascii"),
        }
    )


@socketio.on("connect", namespace="/persona")
def handle_persona_connect() -> None:
    _emit_persona_state("idle", "brain_loop", "")


@socketio.on("message")
def handle_message(data):
    text = data.get("text") if isinstance(data, dict) else None
    if not isinstance(text, str) or not text.strip():
        emit("response", {"text": "Please send a non-empty message."})
        return

    try:
        response = _process_message(text.strip())
    except Exception:
        app.logger.exception("WebSocket message failed")
        emit("response", {"text": "The message could not be processed."})
        return

    emit("response", {"text": response})


from interface.reflex import register_reflex_handler
register_reflex_handler(_emit_persona_alert)

if __name__ == "__main__":
    run_startup_script()
    start_brain_loop()
    try:
        socketio.run(
            app,
            host="0.0.0.0",
            port=5000,
            debug=False,
            use_reloader=False,
            allow_unsafe_werkzeug=True,
        )
    finally:
        stop_brain_loop()
