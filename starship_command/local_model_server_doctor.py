from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

try:
    from .crew_output_validator import allowed_divisions_from_registry, validate_crew_output
    from .crew_prompt_pack import render_prompt_profile
    from .local_model_adapter import (
        JSONRequester,
        LOCAL_HOSTS,
        LocalModelBridgeError,
        extract_chat_text,
        join_endpoint,
        request_json,
        require_local_http_endpoint,
    )
    from .starship_core import REGISTRY_PATH, load_registry
except ImportError:  # pragma: no cover - direct script execution path
    from crew_output_validator import allowed_divisions_from_registry, validate_crew_output
    from crew_prompt_pack import render_prompt_profile
    from local_model_adapter import (
        JSONRequester,
        LOCAL_HOSTS,
        LocalModelBridgeError,
        extract_chat_text,
        join_endpoint,
        request_json,
        require_local_http_endpoint,
    )
    from starship_core import REGISTRY_PATH, load_registry


Timer = Callable[[], float]

CONTEXT_KEYS = {
    "context_window",
    "context_length",
    "context_size",
    "max_context_length",
    "max_context_window",
    "n_ctx",
    "ctx_size",
    "loaded_context_length",
    "loaded_context_window",
    "contextWindow",
    "maxContextLength",
}

LIKELY_UNREACHABLE_CAUSES = [
    "LM Studio is not running.",
    "LM Studio local server is disabled.",
    "The configured endpoint or port differs from the running server.",
    "The expected model is not loaded or visible through the local endpoint.",
]
LOCAL_MODEL_SAFETY_RULE = "Do not edit files, claim to run tools, call external services, or make autonomous changes."


@dataclass(frozen=True)
class ObservedModel:
    model_id: str
    registry_role_id: str
    role_classification: str
    human_observed_context_window: int | None = None


@dataclass(frozen=True)
class ReadinessTest:
    model_id: str
    prompt_name: str
    prompt: str
    system_prompt: str
    role_classification: str
    max_tokens: int
    prompt_profile: str = ""


@dataclass(frozen=True)
class DoctorConfig:
    endpoint: str
    timeout_seconds: float
    list_models_path: str
    chat_completions_path: str
    allow_non_local_endpoint: bool
    low_context_window_threshold: int
    temperature: float
    max_tokens: int
    registry_models: list[ObservedModel]
    observed_models: list[ObservedModel]
    readiness_tests: list[ReadinessTest]
    allowed_divisions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ModelInfo:
    model_id: str
    context_window: int | None
    raw: dict[str, Any]


def _string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LocalModelBridgeError(f"{name} must be a non-empty string")
    return value.strip()


def _float(value: object, name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise LocalModelBridgeError(f"{name} must be numeric") from exc


def _int(value: object, name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise LocalModelBridgeError(f"{name} must be an integer") from exc


def _bool(value: object, name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise LocalModelBridgeError(f"{name} must be true or false")


def _optional_string(value: object, name: str) -> str:
    if value is None:
        return ""
    return _string(value, name)


def validate_doctor_endpoint(endpoint: str, allow_non_local_endpoint: bool = False) -> str:
    if not allow_non_local_endpoint:
        return require_local_http_endpoint(endpoint)
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"}:
        raise LocalModelBridgeError("Endpoint must use http:// or https://")
    if parsed.query or parsed.fragment:
        raise LocalModelBridgeError("Endpoint must not include query strings or fragments")
    if parsed.hostname not in LOCAL_HOSTS:
        # The flag is intentionally explicit because this tool is designed for
        # localhost. Keeping the check visible prevents accidental external use.
        return endpoint.rstrip("/")
    return endpoint.rstrip("/")


def load_doctor_config(
    registry_path: Path = REGISTRY_PATH,
    *,
    endpoint_override: str | None = None,
    timeout_override: float | None = None,
) -> DoctorConfig:
    registry = load_registry(registry_path)
    bridge = registry.get("local_model_bridge")
    raw_doctor = registry.get("local_model_server_doctor")
    if not isinstance(bridge, dict):
        raise LocalModelBridgeError("command_registry.yaml must define local_model_bridge")
    if not isinstance(raw_doctor, dict):
        raise LocalModelBridgeError("command_registry.yaml must define local_model_server_doctor")

    allow_non_local = _bool(raw_doctor.get("allow_non_local_endpoint", False), "allow_non_local_endpoint")
    endpoint = validate_doctor_endpoint(
        endpoint_override or _string(bridge.get("endpoint"), "local_model_bridge.endpoint"),
        allow_non_local,
    )
    timeout_seconds = timeout_override if timeout_override is not None else _float(
        raw_doctor.get("timeout_seconds", bridge.get("timeout_seconds", 60)),
        "local_model_server_doctor.timeout_seconds",
    )
    if timeout_seconds <= 0:
        raise LocalModelBridgeError("timeout_seconds must be greater than zero")

    observed_models = parse_observed_models(raw_doctor.get("user_observed_models", []))
    registry_models = parse_observed_models(raw_doctor.get("registry_models", []))
    if not registry_models:
        registry_models = observed_models
    return DoctorConfig(
        endpoint=endpoint,
        timeout_seconds=float(timeout_seconds),
        list_models_path=_string(
            raw_doctor.get("list_models_path", bridge.get("list_models_path", "/models")),
            "local_model_server_doctor.list_models_path",
        ),
        chat_completions_path=_string(
            raw_doctor.get("chat_completions_path", bridge.get("chat_completions_path", "/chat/completions")),
            "local_model_server_doctor.chat_completions_path",
        ),
        allow_non_local_endpoint=allow_non_local,
        low_context_window_threshold=_int(
            raw_doctor.get("low_context_window_threshold", 2048),
            "local_model_server_doctor.low_context_window_threshold",
        ),
        temperature=_float(raw_doctor.get("temperature", bridge.get("temperature", 0.1)), "temperature"),
        max_tokens=_int(raw_doctor.get("max_tokens", bridge.get("max_tokens", 600)), "max_tokens"),
        registry_models=registry_models,
        observed_models=observed_models,
        readiness_tests=parse_readiness_tests(raw_doctor.get("readiness_tests", []), registry_models + observed_models),
        allowed_divisions=allowed_divisions_from_registry(registry),
    )


def parse_observed_models(raw_models: object) -> list[ObservedModel]:
    if not isinstance(raw_models, list):
        raise LocalModelBridgeError("local_model_server_doctor.user_observed_models must be a list")
    models: list[ObservedModel] = []
    for item in raw_models:
        if not isinstance(item, dict):
            raise LocalModelBridgeError("Each observed model entry must be a mapping")
        context = item.get("human_observed_context_window")
        models.append(
            ObservedModel(
                model_id=_string(item.get("model_id"), "user_observed_models.model_id"),
                registry_role_id=_string(item.get("registry_role_id"), "user_observed_models.registry_role_id"),
                role_classification=_string(
                    item.get("role_classification", "unavailable"),
                    "user_observed_models.role_classification",
                ),
                human_observed_context_window=None if context is None else _int(context, "human_observed_context_window"),
            )
        )
    return models


def parse_readiness_tests(raw_tests: object, observed_models: list[ObservedModel]) -> list[ReadinessTest]:
    if not isinstance(raw_tests, list):
        raise LocalModelBridgeError("local_model_server_doctor.readiness_tests must be a list")
    classification_by_model = {item.model_id: item.role_classification for item in observed_models}
    tests: list[ReadinessTest] = []
    for item in raw_tests:
        if not isinstance(item, dict):
            raise LocalModelBridgeError("Each readiness test entry must be a mapping")
        model_id = _string(item.get("model_id"), "readiness_tests.model_id")
        prompt_profile = _optional_string(item.get("prompt_profile"), "readiness_tests.prompt_profile")
        prompt = _optional_string(
            item.get("mission")
            or item.get("task")
            or item.get("context")
            or item.get("observations")
            or item.get("prompt"),
            "readiness_tests.prompt",
        )
        system_prompt = _optional_string(item.get("system_prompt"), "readiness_tests.system_prompt")
        if not prompt:
            raise LocalModelBridgeError("readiness_tests prompt, mission, task, context, or observations is required")
        if not prompt_profile and not system_prompt:
            raise LocalModelBridgeError("readiness_tests.system_prompt is required when prompt_profile is not set")
        tests.append(
            ReadinessTest(
                model_id=model_id,
                prompt_name=_string(
                    item.get("prompt_name", prompt_profile),
                    "readiness_tests.prompt_name",
                ),
                prompt=prompt,
                system_prompt=system_prompt,
                role_classification=_string(
                    item.get("role_classification", classification_by_model.get(model_id, "unavailable")),
                    "readiness_tests.role_classification",
                ),
                max_tokens=_int(item.get("max_tokens", 300), "readiness_tests.max_tokens"),
                prompt_profile=prompt_profile,
            )
        )
    return tests


def _coerce_context_value(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float) and value > 0:
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        return parsed if parsed > 0 else None
    return None


def extract_context_window(raw_model: object) -> int | None:
    if not isinstance(raw_model, dict):
        return None
    for key in CONTEXT_KEYS:
        if key in raw_model:
            parsed = _coerce_context_value(raw_model[key])
            if parsed is not None:
                return parsed
    for value in raw_model.values():
        if isinstance(value, dict):
            parsed = extract_context_window(value)
            if parsed is not None:
                return parsed
        elif isinstance(value, list):
            for item in value:
                parsed = extract_context_window(item)
                if parsed is not None:
                    return parsed
    return None


def list_model_infos(config: DoctorConfig, requester: JSONRequester = request_json) -> list[ModelInfo]:
    response = requester(
        "GET",
        join_endpoint(config.endpoint, config.list_models_path),
        None,
        config.timeout_seconds,
    )
    raw_models = response.get("data")
    if not isinstance(raw_models, list):
        raise LocalModelBridgeError("Local model /models response did not contain a data list")

    models: list[ModelInfo] = []
    for item in raw_models:
        if isinstance(item, str):
            models.append(ModelInfo(model_id=item, context_window=None, raw={"id": item}))
        elif isinstance(item, dict) and isinstance(item.get("id"), str):
            models.append(ModelInfo(model_id=item["id"], context_window=extract_context_window(item), raw=item))
    return models


def check_endpoint(config: DoctorConfig, requester: JSONRequester = request_json) -> dict[str, Any]:
    try:
        models = list_model_infos(config, requester)
    except LocalModelBridgeError as exc:
        return {"endpoint": config.endpoint, "reachable": False, "error": str(exc), "models": []}
    return {"endpoint": config.endpoint, "reachable": True, "error": "", "models": models}


def context_warning(context_window: int | None, threshold: int, source: str = "programmatic") -> str:
    if context_window is None:
        return "context_window unknown; verify in LM Studio before comparing model quality"
    if context_window <= threshold:
        return (
            f"low {source} context window ({context_window}); likely quality limitation "
            "for code/project reasoning"
        )
    return ""


def match_observed_model(observed: ObservedModel, visible_ids: set[str]) -> bool:
    return observed.model_id in visible_ids


def visible_registry_models(config: DoctorConfig, visible_ids: set[str]) -> list[ObservedModel]:
    return [model for model in config.registry_models if match_observed_model(model, visible_ids)]


def missing_observed_models(config: DoctorConfig, visible_ids: set[str]) -> list[ObservedModel]:
    return [model for model in config.observed_models if not match_observed_model(model, visible_ids)]


def run_readiness_test(
    config: DoctorConfig,
    test: ReadinessTest,
    requester: JSONRequester = request_json,
    timer: Timer = time.perf_counter,
) -> dict[str, Any]:
    payload = build_readiness_payload(config, test)
    started = timer()
    response = requester(
        "POST",
        join_endpoint(config.endpoint, config.chat_completions_path),
        payload,
        config.timeout_seconds,
    )
    latency_seconds = timer() - started
    response_text = extract_chat_text(response)
    validation = validate_crew_output(
        prompt_profile=test.prompt_profile or test.prompt_name,
        response_text=response_text,
        prompt_context=test.prompt,
        allowed_divisions=config.allowed_divisions,
    )
    return {
        "model_id": test.model_id,
        "prompt_name": test.prompt_name,
        "prompt_profile": test.prompt_profile or test.prompt_name,
        "role_classification": test.role_classification,
        "latency_seconds": latency_seconds,
        "response_preview": preview_text(response_text),
        "error": "",
        **validation.as_dict(),
    }


def build_readiness_payload(config: DoctorConfig, test: ReadinessTest) -> dict[str, Any]:
    system_prompt, user_prompt = render_readiness_messages(test)
    return {
        "model": test.model_id,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": config.temperature,
        "max_tokens": test.max_tokens or config.max_tokens,
        "stream": False,
    }


def render_readiness_messages(test: ReadinessTest) -> tuple[str, str]:
    if test.prompt_profile:
        rendered = render_prompt_profile(
            test.prompt_profile,
            {
                "mission": test.prompt,
                "task": test.prompt,
                "context": test.prompt,
                "observations": test.prompt,
            },
        )
        system_prompt = rendered.system_prompt
        if LOCAL_MODEL_SAFETY_RULE not in system_prompt:
            system_prompt = f"{system_prompt}\n{LOCAL_MODEL_SAFETY_RULE}"
        return system_prompt, rendered.user_prompt
    return f"{test.system_prompt} {LOCAL_MODEL_SAFETY_RULE}", test.prompt


def build_readiness_dry_run(config: DoctorConfig) -> dict[str, Any]:
    return {
        "dry_run": True,
        "network_call_made": False,
        "endpoint": config.endpoint,
        "url": join_endpoint(config.endpoint, config.chat_completions_path),
        "timeout_seconds": config.timeout_seconds,
        "tests": [
            {
                "model_id": test.model_id,
                "prompt_name": test.prompt_name,
                "prompt_profile": test.prompt_profile or test.prompt_name,
                "role_classification": test.role_classification,
                "payload": build_readiness_payload(config, test),
            }
            for test in config.readiness_tests
        ],
    }


def preview_text(text: str, limit: int = 360) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 3].rstrip() + "..."


def build_readiness_report(
    config: DoctorConfig,
    requester: JSONRequester = request_json,
    timer: Timer = time.perf_counter,
) -> dict[str, Any]:
    endpoint = check_endpoint(config, requester)
    if not endpoint["reachable"]:
        return {
            "endpoint": config.endpoint,
            "endpoint_reachable": False,
            "models_visible": [],
            "registry_models_visible": [],
            "user_observed_models_missing": [model.model_id for model in config.observed_models],
            "models_tested": [],
            "failures": [endpoint["error"]],
            "human_judgment_required": True,
        }

    model_infos = endpoint["models"]
    info_by_id = {model.model_id: model for model in model_infos}
    visible_ids = set(info_by_id)
    models_tested: list[dict[str, Any]] = []
    failures: list[str] = []

    for test in config.readiness_tests:
        if test.model_id not in visible_ids:
            continue
        try:
            result = run_readiness_test(config, test, requester, timer)
        except LocalModelBridgeError as exc:
            failures.append(f"{test.model_id}: {exc}")
            result = {
                "model_id": test.model_id,
                "prompt_name": test.prompt_name,
                "prompt_profile": test.prompt_profile or test.prompt_name,
                "role_classification": test.role_classification,
                "latency_seconds": None,
                "response_preview": "",
                "error": str(exc),
                "schema_valid": False,
                "division_vocabulary_valid": "not_applicable",
                "warnings": [],
                "missing_required_fields": [],
                "invalid_divisions": [],
                "trust_gate": "fail",
                "human_review_required": True,
            }
        model_info = info_by_id.get(test.model_id)
        observed = next((item for item in config.observed_models if item.model_id == test.model_id), None)
        result["context_window"] = model_info.context_window if model_info else None
        result["human_observed_context_window"] = (
            observed.human_observed_context_window if observed else None
        )
        context_warnings = model_warnings(
            result["context_window"],
            result["human_observed_context_window"],
            config.low_context_window_threshold,
        )
        result["warnings"] = list(dict.fromkeys([*result.get("warnings", []), *context_warnings]))
        models_tested.append(result)

    visible_models = []
    for model in model_infos:
        observed = next((item for item in config.observed_models if item.model_id == model.model_id), None)
        registry_model = next((item for item in config.registry_models if item.model_id == model.model_id), None)
        known_model = observed or registry_model
        role = known_model.role_classification if known_model else classify_unregistered_model(model.model_id)
        visible_models.append(
            {
                "model_id": model.model_id,
                "context_window": model.context_window,
                "human_observed_context_window": observed.human_observed_context_window if observed else None,
                "role_classification": role,
                "warnings": model_warnings(
                    model.context_window,
                    observed.human_observed_context_window if observed else None,
                    config.low_context_window_threshold,
                ),
            }
        )

    return {
        "endpoint": config.endpoint,
        "endpoint_reachable": True,
        "models_visible": visible_models,
        "registry_models_visible": [model.model_id for model in visible_registry_models(config, visible_ids)],
        "user_observed_models_missing": [model.model_id for model in missing_observed_models(config, visible_ids)],
        "models_tested": models_tested,
        "failures": failures,
        "human_judgment_required": True,
    }


def model_warnings(
    context_window: int | None,
    human_observed_context_window: int | None,
    threshold: int,
) -> list[str]:
    warnings: list[str] = []
    programmatic_warning = context_warning(context_window, threshold, "programmatic")
    if programmatic_warning:
        warnings.append(programmatic_warning)
    if human_observed_context_window is not None:
        observed_warning = context_warning(human_observed_context_window, threshold, "human-observed")
        if observed_warning:
            warnings.append(observed_warning)
    return warnings


def classify_unregistered_model(model_id: str) -> str:
    lowered = model_id.casefold()
    if "embed" in lowered:
        return "embedding/retrieval candidate"
    if "vl" in lowered or "vision" in lowered:
        return "visual model candidate"
    if "coder" in lowered or "code" in lowered:
        return "deep Engineering consult candidate"
    if "3b" in lowered:
        return "fast triage candidate"
    return "unclassified local model"


def format_check(result: dict[str, Any]) -> str:
    lines = [
        "Starship Local Model Server Doctor - Endpoint Check",
        f"Endpoint: {result['endpoint']}",
        f"Reachable: {'yes' if result['reachable'] else 'no'}",
    ]
    if result["error"]:
        lines.append(f"Error: {result['error']}")
    else:
        lines.append(f"Visible model count: {len(result['models'])}")
    return "\n".join(lines)


def format_model_list(config: DoctorConfig, model_infos: list[ModelInfo]) -> str:
    visible_ids = {model.model_id for model in model_infos}
    lines = [
        "Starship Local Model Server Doctor - Model List",
        f"Endpoint: {config.endpoint}",
        "Visible models:",
    ]
    for model in model_infos:
        context = str(model.context_window) if model.context_window is not None else "unknown"
        lines.append(f"- {model.model_id} | context_window: {context}")
    lines.append("Registry/user-observed models visible:")
    visible = visible_registry_models(config, visible_ids)
    lines.extend(f"- {model.model_id} ({model.registry_role_id})" for model in visible)
    lines.append("User-observed models missing:")
    missing = missing_observed_models(config, visible_ids)
    lines.extend(f"- {model.model_id} ({model.registry_role_id})" for model in missing)
    if not missing:
        lines.append("- None")
    return "\n".join(lines)


def format_context(value: object) -> str:
    return "unknown" if value is None else str(value)


def format_latency(value: object) -> str:
    return "not measured" if value is None else f"{float(value):.3f}s"


def format_validation_value(value: object) -> str:
    if isinstance(value, bool):
        return "pass" if value else "fail"
    return str(value)


def format_readiness_report(report: dict[str, Any]) -> str:
    lines = [
        "Starship Local Model Server Doctor - Readiness Report",
        f"Endpoint: {report['endpoint']}",
        f"Endpoint reachable: {'yes' if report['endpoint_reachable'] else 'no'}",
        "Human judgment required: yes",
    ]
    if not report["endpoint_reachable"]:
        lines.append("Failures/timeouts:")
        lines.extend(f"- {failure}" for failure in report["failures"])
        lines.append("Likely causes:")
        lines.extend(f"- {cause}" for cause in LIKELY_UNREACHABLE_CAUSES)
        return "\n".join(lines)

    lines.append("Models visible:")
    for model in report["models_visible"]:
        lines.append(
            f"- {model['model_id']} | context_window: {format_context(model['context_window'])} | "
            f"human_observed_context_window: {format_context(model['human_observed_context_window'])} | "
            f"role: {model['role_classification']}"
        )
        for warning in model["warnings"]:
            lines.append(f"  warning: {warning}")

    lines.append("Registry/user-observed models visible:")
    if report["registry_models_visible"]:
        lines.extend(f"- {model_id}" for model_id in report["registry_models_visible"])
    else:
        lines.append("- None")

    lines.append("User-observed models missing:")
    if report["user_observed_models_missing"]:
        lines.extend(f"- {model_id}" for model_id in report["user_observed_models_missing"])
    else:
        lines.append("- None")

    lines.append("Models tested:")
    if report["models_tested"]:
        for result in report["models_tested"]:
            lines.append(
                f"- {result['model_id']} | role: {result['role_classification']} | "
                f"profile: {result.get('prompt_profile', result['prompt_name'])} | "
                f"context_window: {format_context(result.get('context_window'))} | "
                f"latency: {format_latency(result['latency_seconds'])}"
            )
            if result["error"]:
                lines.append(f"  error: {result['error']}")
            else:
                lines.append(f"  response_preview: {result['response_preview']}")
            lines.append("  Validation:")
            lines.append(f"  - Schema: {format_validation_value(result.get('schema_valid', False))}")
            lines.append(f"  - Division names: {result.get('division_vocabulary_valid', 'not_applicable')}")
            lines.append(f"  - Warnings: {', '.join(result.get('warnings', [])) or 'none'}")
            lines.append(f"  - Trust gate: {result.get('trust_gate', 'fail')}")
            lines.append("  - Human review required: yes")
            if result.get("missing_required_fields"):
                lines.append(f"  missing_required_fields: {', '.join(result['missing_required_fields'])}")
            if result.get("invalid_divisions"):
                lines.append(f"  invalid_divisions: {', '.join(result['invalid_divisions'])}")
            for warning in result["warnings"]:
                lines.append(f"  warning: {warning}")
    else:
        lines.append("- None")

    if report["failures"]:
        lines.append("Failures/timeouts:")
        lines.extend(f"- {failure}" for failure in report["failures"])
    else:
        lines.append("Failures/timeouts: none")

    lines.append("Note: context_window unknown means the endpoint did not expose it; verify in LM Studio.")
    lines.append("Note: do not compare models directly unless context windows are recorded or explicitly unknown.")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Diagnose the configured local LM Studio endpoint for Starship Command.",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=REGISTRY_PATH,
        help="Path to command_registry.yaml. Defaults to starship_command/command_registry.yaml.",
    )
    parser.add_argument("--endpoint", help="Override endpoint. Refuses non-local endpoints unless registry flag allows it.")
    parser.add_argument("--timeout", type=float, help="Override timeout in seconds.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="Check whether the configured local endpoint responds.")
    subparsers.add_parser("list-models", help="List visible models and known registry/user-observed matches.")
    subparsers.add_parser("dry-run-readiness", help="Render configured readiness request payloads without sending them.")
    subparsers.add_parser("readiness", help="Run lightweight readiness tests for visible configured models.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_doctor_config(args.registry, endpoint_override=args.endpoint, timeout_override=args.timeout)
        if args.command == "check":
            print(format_check(check_endpoint(config)))
            return 0
        if args.command == "list-models":
            print(format_model_list(config, list_model_infos(config)))
            return 0
        if args.command == "dry-run-readiness":
            import json

            print(json.dumps(build_readiness_dry_run(config), indent=2))
            return 0
        if args.command == "readiness":
            print(format_readiness_report(build_readiness_report(config)))
            return 0
    except LocalModelBridgeError as exc:
        print(f"Local model server doctor error: {exc}", file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
