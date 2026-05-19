from __future__ import annotations

import base64
import subprocess
import sys
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_socketio import SocketIO, emit


ROOT = Path(__file__).resolve().parents[1]
STARTUP_SCRIPT = ROOT / "scripts" / "startup.py"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import bot  # noqa: E402
import stt  # noqa: E402
import tts  # noqa: E402


app = Flask(__name__, static_folder="static", static_url_path="")
socketio = SocketIO(app, cors_allowed_origins="*")


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


def _message_from_json() -> tuple[str | None, tuple | None]:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return None, (jsonify({"error": "Expected JSON object"}), 400)

    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        return None, (jsonify({"error": "message must be a non-empty string"}), 400)

    return message.strip(), None


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.post("/chat")
def chat():
    message, error = _message_from_json()
    if error is not None:
        return error

    try:
        response = bot.respond(message)
    except Exception:
        app.logger.exception("Chat request failed")
        return jsonify({"error": "Chat request failed"}), 500

    return jsonify({"response": response})


@app.post("/voice")
def voice():
    audio_bytes = request.get_data(cache=False)
    if not audio_bytes:
        return jsonify({"error": "Expected raw audio bytes"}), 400

    try:
        transcript = stt.transcribe(audio_bytes)
        response = bot.respond(transcript)
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


@socketio.on("message")
def handle_message(data):
    text = data.get("text") if isinstance(data, dict) else None
    if not isinstance(text, str) or not text.strip():
        emit("response", {"text": "Please send a non-empty message."})
        return

    try:
        response = bot.respond(text.strip())
    except Exception:
        app.logger.exception("WebSocket message failed")
        emit("response", {"text": "The message could not be processed."})
        return

    emit("response", {"text": response})


if __name__ == "__main__":
    run_startup_script()
    socketio.run(
        app,
        host="0.0.0.0",
        port=5000,
        debug=False,
        use_reloader=False,
        allow_unsafe_werkzeug=True,
    )
