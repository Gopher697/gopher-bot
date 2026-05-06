from __future__ import annotations

import json
import threading
import urllib.request

from starship_command import command_operations_gui


def test_local_model_readiness_output_uses_model_operations_helper(monkeypatch) -> None:
    calls = []

    def fake_readiness() -> str:
        calls.append("readiness")
        return "formatted model operations readiness report"

    monkeypatch.setattr(command_operations_gui, "build_model_operations_readiness_output", fake_readiness)

    output = command_operations_gui.build_local_model_readiness_output()

    assert output == "formatted model operations readiness report"
    assert calls == ["readiness"]


def test_model_operations_status_endpoint_updates_output_without_live_lm_studio(monkeypatch) -> None:
    def fake_status() -> str:
        return "Starship Model Operations - Local Model Status\nEndpoint reachable: no"

    monkeypatch.setattr(command_operations_gui, "build_model_operations_status_output", fake_status)

    server = command_operations_gui.CommandOperationsServer(("127.0.0.1", 0))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/model-operations/status",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert payload["result"]["output"].startswith("Starship Model Operations")
    assert payload["state"]["output"] == payload["result"]["output"]


def test_model_operations_reload_endpoint_requires_authorized_payload(monkeypatch) -> None:
    calls = []

    def fake_reload(*, target_context: int, captain_authorized: bool) -> str:
        calls.append((target_context, captain_authorized))
        return "reload refused"

    monkeypatch.setattr(command_operations_gui, "authorized_coder_context_reload_output", fake_reload)

    server = command_operations_gui.CommandOperationsServer(("127.0.0.1", 0))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/model-operations/reload-coder",
            data=json.dumps({"target_context": 4096, "captain_authorized": False}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert calls == [(4096, False)]
    assert payload["result"]["output"] == "reload refused"
