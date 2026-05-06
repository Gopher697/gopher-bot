from __future__ import annotations

import argparse
import json
import socket
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

try:
    from .starship_core import REGISTRY_PATH, load_registry
except ImportError:  # pragma: no cover - direct script execution path
    from starship_core import REGISTRY_PATH, load_registry


JSONRequester = Callable[[str, str, dict[str, Any] | None, float], dict[str, Any]]
Timer = Callable[[], float]

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class LocalModelBridgeError(RuntimeError):
    """Raised when the local model bridge cannot safely complete a request."""


@dataclass(frozen=True)
class LocalModelConfig:
    endpoint: str
    model: str
    timeout_seconds: float
    temperature: float
    max_tokens: int
    engineering_test_prompt: str
    list_models_path: str = "/models"
    chat_completions_path: str = "/chat/completions"


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LocalModelBridgeError(f"local_model_bridge.{name} must be a non-empty string")
    return value.strip()


def _float(value: object, name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise LocalModelBridgeError(f"local_model_bridge.{name} must be numeric") from exc


def _int(value: object, name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise LocalModelBridgeError(f"local_model_bridge.{name} must be an integer") from exc


def require_local_http_endpoint(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    if parsed.scheme != "http":
        raise LocalModelBridgeError("Local model endpoint must use http:// for this proof adapter")
    if parsed.hostname not in LOCAL_HOSTS:
        raise LocalModelBridgeError(
            "Local model endpoint must be localhost, 127.0.0.1, or ::1; external API endpoints are refused"
        )
    if parsed.query or parsed.fragment:
        raise LocalModelBridgeError("Local model endpoint must not include query strings or fragments")
    return endpoint.rstrip("/")


def load_local_model_config(
    registry_path: Path = REGISTRY_PATH,
    *,
    endpoint_override: str | None = None,
    model_override: str | None = None,
    timeout_override: float | None = None,
) -> LocalModelConfig:
    registry = load_registry(registry_path)
    raw_config = registry.get("local_model_bridge")
    if not isinstance(raw_config, dict):
        raise LocalModelBridgeError("command_registry.yaml must define local_model_bridge")

    endpoint = require_local_http_endpoint(
        endpoint_override or _string(raw_config.get("endpoint"), "endpoint")
    )
    model = model_override or _string(raw_config.get("default_model"), "default_model")
    timeout_seconds = timeout_override if timeout_override is not None else _float(
        raw_config.get("timeout_seconds", 60),
        "timeout_seconds",
    )
    if timeout_seconds <= 0:
        raise LocalModelBridgeError("local_model_bridge.timeout_seconds must be greater than zero")

    return LocalModelConfig(
        endpoint=endpoint,
        model=model,
        timeout_seconds=float(timeout_seconds),
        temperature=_float(raw_config.get("temperature", 0.1), "temperature"),
        max_tokens=_int(raw_config.get("max_tokens", 600), "max_tokens"),
        engineering_test_prompt=_string(
            raw_config.get("engineering_test_prompt"),
            "engineering_test_prompt",
        ),
        list_models_path=_string(raw_config.get("list_models_path", "/models"), "list_models_path"),
        chat_completions_path=_string(
            raw_config.get("chat_completions_path", "/chat/completions"),
            "chat_completions_path",
        ),
    )


def join_endpoint(endpoint: str, path: str) -> str:
    clean_path = path if path.startswith("/") else f"/{path}"
    return f"{endpoint.rstrip('/')}{clean_path}"


def request_json(method: str, url: str, payload: dict[str, Any] | None, timeout: float) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "StarshipCommandLocalModelBridge/0.1",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")[:500]
        raise LocalModelBridgeError(
            f"Local model endpoint returned HTTP {exc.code} for {url}: {error_body}"
        ) from exc
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        raise LocalModelBridgeError(
            f"Could not reach local model endpoint {url}. Is LM Studio running with the local server enabled?"
        ) from exc

    try:
        decoded = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise LocalModelBridgeError(f"Local model endpoint returned non-JSON response for {url}") from exc
    if not isinstance(decoded, dict):
        raise LocalModelBridgeError(f"Local model endpoint returned a non-object JSON response for {url}")
    return decoded


def list_models(
    config: LocalModelConfig,
    requester: JSONRequester = request_json,
) -> list[str]:
    response = requester(
        "GET",
        join_endpoint(config.endpoint, config.list_models_path),
        None,
        config.timeout_seconds,
    )
    raw_models = response.get("data")
    if not isinstance(raw_models, list):
        raise LocalModelBridgeError("Local model /models response did not contain a data list")

    models: list[str] = []
    for item in raw_models:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            models.append(item["id"])
        elif isinstance(item, str):
            models.append(item)
    return models


def ensure_model_available(
    config: LocalModelConfig,
    requester: JSONRequester = request_json,
) -> list[str]:
    models = list_models(config, requester)
    if config.model not in models:
        listed = ", ".join(models) if models else "[none listed]"
        raise LocalModelBridgeError(f"Configured model {config.model!r} was not listed by LM Studio. Models: {listed}")
    return models


def extract_chat_text(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LocalModelBridgeError("Chat completion response did not include choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise LocalModelBridgeError("Chat completion choice was not an object")
    message = first.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise LocalModelBridgeError("Chat completion response did not include message.content")
    return message["content"].strip()


def run_engineering_test(
    config: LocalModelConfig,
    requester: JSONRequester = request_json,
    timer: Timer = time.perf_counter,
) -> dict[str, Any]:
    ensure_model_available(config, requester)
    payload = {
        "model": config.model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a local Engineering review assistant for Starship Command. "
                    "Do not edit files, claim to run tools, or call external services. "
                    "Answer with one suggested unit test and a short rationale."
                ),
            },
            {"role": "user", "content": config.engineering_test_prompt},
        ],
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "stream": False,
    }

    started = timer()
    response = requester(
        "POST",
        join_endpoint(config.endpoint, config.chat_completions_path),
        payload,
        config.timeout_seconds,
    )
    latency_seconds = timer() - started
    return {
        "model": config.model,
        "endpoint": config.endpoint,
        "latency_seconds": latency_seconds,
        "response_text": extract_chat_text(response),
        "human_usability_judgment": "pending",
        "usability_note": "Human review required; the adapter does not auto-grade model quality.",
    }


def format_models(config: LocalModelConfig, models: list[str]) -> str:
    lines = [
        "Starship Local Model Bridge - Model List",
        f"Endpoint: {config.endpoint}",
        f"Configured model: {config.model}",
        "Models:",
    ]
    lines.extend(f"- {model}" for model in models)
    return "\n".join(lines)


def format_engineering_result(result: dict[str, Any]) -> str:
    return "\n".join(
        [
            "Starship Local Model Bridge - Engineering Test",
            f"Endpoint: {result['endpoint']}",
            f"Model: {result['model']}",
            f"Latency: {result['latency_seconds']:.3f}s",
            f"Human usability judgment: {result['human_usability_judgment']}",
            f"Usability note: {result['usability_note']}",
            "",
            "Response:",
            result["response_text"],
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Narrow local LM Studio bridge proof for Starship Command.",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=REGISTRY_PATH,
        help="Path to command_registry.yaml. Defaults to starship_command/command_registry.yaml.",
    )
    parser.add_argument("--endpoint", help="Override local endpoint. Must be http://localhost, 127.0.0.1, or ::1.")
    parser.add_argument("--model", help="Override configured model name.")
    parser.add_argument("--timeout", type=float, help="Override request timeout in seconds.")

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("config", help="Show the configured local model bridge target.")
    subparsers.add_parser("list-models", help="Call the local /models endpoint and list available models.")
    subparsers.add_parser("test-engineering", help="Run the fixed Engineering behavior test prompt.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_local_model_config(
            args.registry,
            endpoint_override=args.endpoint,
            model_override=args.model,
            timeout_override=args.timeout,
        )
        if args.command == "config":
            print(f"Endpoint: {config.endpoint}")
            print(f"Model: {config.model}")
            print(f"Timeout: {config.timeout_seconds:g}s")
            print("Scope: local LM Studio OpenAI-compatible endpoint only")
            return 0
        if args.command == "list-models":
            print(format_models(config, list_models(config)))
            return 0
        if args.command == "test-engineering":
            print(format_engineering_result(run_engineering_test(config)))
            return 0
    except LocalModelBridgeError as exc:
        print(f"Local model bridge error: {exc}", file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
