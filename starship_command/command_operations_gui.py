from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

try:
    from .model_operations import (
        authorized_coder_context_reload_output,
        build_model_operations_readiness_output,
        build_model_operations_status_output,
        build_profile_compliance_output,
        build_profile_load_estimate_output,
        build_profile_readiness_output,
        prepare_profile_reload_output,
        prepare_coder_retest_output,
    )
    from .starship_core import (
        add_codex_order,
        add_handoff,
        add_route_assignment,
        create_initial_state,
        deploy_specialist,
        load_registry,
        state_snapshot,
    )
except ImportError:  # pragma: no cover - direct script execution path
    from model_operations import (
        authorized_coder_context_reload_output,
        build_model_operations_readiness_output,
        build_model_operations_status_output,
        build_profile_compliance_output,
        build_profile_load_estimate_output,
        build_profile_readiness_output,
        prepare_profile_reload_output,
        prepare_coder_retest_output,
    )
    from starship_core import (
        add_codex_order,
        add_handoff,
        add_route_assignment,
        create_initial_state,
        deploy_specialist,
        load_registry,
        state_snapshot,
    )


BASE_DIR = Path(__file__).resolve().parent
GUI_DIR = BASE_DIR / "gui"


def build_local_model_readiness_output() -> str:
    return build_model_operations_readiness_output()


class CommandOperationsServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int]):
        super().__init__(server_address, CommandOperationsHandler)
        self.registry = load_registry()
        self.state = create_initial_state(self.registry)


class CommandOperationsHandler(BaseHTTPRequestHandler):
    server: CommandOperationsServer

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write("Command Operations: " + format % args + "\n")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            self._send_json(state_snapshot(self.server.state, self.server.registry))
            return
        if parsed.path == "/api/registry":
            self._send_json(self.server.registry)
            return
        self._serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            payload = self._read_json()
            if parsed.path == "/api/route":
                result = add_route_assignment(self.server.state, payload.get("mission", ""), self.server.registry)
            elif parsed.path == "/api/deploy-specialist":
                result = deploy_specialist(self.server.state, payload.get("mission", ""), self.server.registry)
            elif parsed.path == "/api/codex-order":
                result = add_codex_order(self.server.state, payload.get("mission", ""), self.server.registry)
            elif parsed.path == "/api/handoff":
                result = add_handoff(self.server.state, payload, self.server.registry)
            elif parsed.path == "/api/local-model-readiness":
                output = build_local_model_readiness_output()
                self.server.state["output"] = output
                result = {"output": output}
            elif parsed.path == "/api/model-operations/status":
                output = build_model_operations_status_output()
                self.server.state["output"] = output
                result = {"output": output}
            elif parsed.path == "/api/model-operations/readiness":
                output = build_model_operations_readiness_output()
                self.server.state["output"] = output
                result = {"output": output}
            elif parsed.path == "/api/model-operations/profile-compliance":
                output = build_profile_compliance_output(
                    model_id=str(payload.get("model_id", "")),
                    profile_id=str(payload.get("profile_id", "")),
                )
                self.server.state["output"] = output
                result = {"output": output}
            elif parsed.path == "/api/model-operations/estimate-profile-load":
                output = build_profile_load_estimate_output(
                    model_id=str(payload.get("model_id", "")),
                    profile_id=str(payload.get("profile_id", "")),
                )
                self.server.state["output"] = output
                result = {"output": output}
            elif parsed.path == "/api/model-operations/prepare-profile-reload":
                output = prepare_profile_reload_output(
                    model_id=str(payload.get("model_id", "")),
                    profile_id=str(payload.get("profile_id", "")),
                )
                self.server.state["output"] = output
                result = {"output": output}
            elif parsed.path == "/api/model-operations/profile-readiness":
                output = build_profile_readiness_output(
                    model_id=str(payload.get("model_id", "")),
                    profile_id=str(payload.get("profile_id", "")),
                )
                self.server.state["output"] = output
                result = {"output": output}
            elif parsed.path == "/api/model-operations/prepare-coder-retest":
                target_context = int(payload.get("target_context", 4096))
                output = prepare_coder_retest_output(target_context=target_context)
                self.server.state["output"] = output
                result = {"output": output}
            elif parsed.path == "/api/model-operations/reload-coder":
                target_context = int(payload.get("target_context", 4096))
                output = authorized_coder_context_reload_output(
                    target_context=target_context,
                    captain_authorized=bool(payload.get("captain_authorized", False)),
                )
                self.server.state["output"] = output
                result = {"output": output}
            elif parsed.path == "/api/model-operations/rerun-readiness":
                output = build_model_operations_readiness_output()
                self.server.state["output"] = output
                result = {"output": output}
            elif parsed.path == "/api/reset":
                self.server.state = create_initial_state(self.server.registry)
                result = {"output": "Command Operations session reset. No persistent truth was created."}
            else:
                self._send_json({"error": "unknown endpoint"}, status=404)
                return
            self._send_json({"result": result, "state": state_snapshot(self.server.state, self.server.registry)})
        except Exception as exc:  # pragma: no cover - defensive HTTP boundary
            self._send_json({"error": str(exc)}, status=400)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("JSON payload must be an object")
        return data

    def _send_json(self, data: object, status: int = 200) -> None:
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, request_path: str) -> None:
        relative = "index.html" if request_path in {"", "/"} else request_path.lstrip("/")
        target = (GUI_DIR / relative).resolve()
        try:
            target.relative_to(GUI_DIR.resolve())
        except ValueError:
            self.send_error(403)
            return
        if not target.is_file():
            self.send_error(404)
            return
        body = target.read_bytes()
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Launch the local Starship Command Operations browser GUI.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Local interface to bind. Default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind. Default: 8765")
    parser.add_argument("--no-open", action="store_true", help="Do not open the browser automatically.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    server = CommandOperationsServer((args.host, args.port))
    host, port = server.server_address
    url = f"http://{host}:{port}/"
    print("Starship Command Operations GUI")
    print("Session state is in memory only and resets on launch.")
    print(f"Open: {url}")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCommand Operations standing down.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
