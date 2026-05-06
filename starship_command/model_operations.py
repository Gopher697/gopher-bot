from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Callable

try:
    from .local_model_adapter import JSONRequester, LocalModelBridgeError, request_json
    from .local_model_server_doctor import (
        DoctorConfig,
        LIKELY_UNREACHABLE_CAUSES,
        ObservedModel,
        build_readiness_report,
        check_endpoint,
        format_context,
        format_latency,
        format_readiness_report,
        load_doctor_config,
        model_warnings,
    )
except ImportError:  # pragma: no cover - direct script execution path
    from local_model_adapter import JSONRequester, LocalModelBridgeError, request_json
    from local_model_server_doctor import (
        DoctorConfig,
        LIKELY_UNREACHABLE_CAUSES,
        ObservedModel,
        build_readiness_report,
        check_endpoint,
        format_context,
        format_latency,
        format_readiness_report,
        load_doctor_config,
        model_warnings,
    )


CODER_14B_MODEL_ID = "qwen2.5-coder-14b-instruct"
SUPPORTED_RETEST_CONTEXTS = {4096, 8192}
FIRST_RETEST_CONTEXT = 4096
CONTEXT_UNKNOWN_WARNING = "context_window unknown; verify in LM Studio before comparing model quality"
LOADED_MODEL_COUNT_WARNING_THRESHOLD = 6
LOADED_MODEL_SIZE_WARNING_THRESHOLD_BYTES = 40 * 1024**3


@dataclass(frozen=True)
class LocalCommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


CommandRunner = Callable[[list[str], float], LocalCommandResult]


def run_local_command(command: list[str], timeout_seconds: float) -> LocalCommandResult:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            stdin=subprocess.DEVNULL,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise LocalModelBridgeError(f"Local command was not found: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise LocalModelBridgeError(f"Local command timed out: {' '.join(command)}") from exc
    return LocalCommandResult(
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout.strip(),
        stderr=completed.stderr.strip(),
    )


def find_lms_executable() -> str | None:
    return shutil.which("lms")


def _command_text(result: LocalCommandResult) -> str:
    return " ".join(result.command)


def _run_lms(
    args: list[str],
    *,
    lms_path: str | None = None,
    runner: CommandRunner = run_local_command,
    timeout_seconds: float = 20,
) -> LocalCommandResult:
    executable = lms_path or find_lms_executable()
    if not executable:
        raise LocalModelBridgeError("LM Studio lms CLI was not found on PATH")
    return runner([executable, *args], timeout_seconds)


def _parse_loaded_models(stdout: str) -> list[dict[str, Any]]:
    if not stdout:
        return []
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise LocalModelBridgeError("lms ps --json returned non-JSON output") from exc
    if not isinstance(parsed, list):
        raise LocalModelBridgeError("lms ps --json did not return a JSON list")
    return [item for item in parsed if isinstance(item, dict)]


def loaded_model_aliases(model: dict[str, Any]) -> set[str]:
    aliases: set[str] = set()
    for key in ("id", "identifier", "modelKey", "path", "indexedModelIdentifier", "selectedVariant"):
        value = model.get(key)
        if isinstance(value, str) and value:
            aliases.add(value)
    variants = model.get("variants")
    if isinstance(variants, list):
        aliases.update(item for item in variants if isinstance(item, str) and item)
    return aliases


def inspect_lms_control(
    *,
    lms_path: str | None = None,
    runner: CommandRunner = run_local_command,
) -> dict[str, Any]:
    executable = lms_path or find_lms_executable()
    if not executable:
        return {
            "available": False,
            "path": "",
            "server_status": "unknown",
            "status_output": "",
            "loaded_models": [],
            "errors": ["LM Studio lms CLI was not found on PATH."],
            "supports_context_reload": False,
        }

    errors: list[str] = []
    status_output = ""
    server_status = "unknown"
    loaded_models: list[dict[str, Any]] = []

    try:
        status = _run_lms(["status"], lms_path=executable, runner=runner)
        status_output = status.stdout or status.stderr
        if status.returncode != 0:
            errors.append(f"`{_command_text(status)}` failed: {status.stderr or status.stdout}")
    except LocalModelBridgeError as exc:
        errors.append(str(exc))

    try:
        server = _run_lms(["server", "status"], lms_path=executable, runner=runner)
        server_status = server.stdout or server.stderr or "unknown"
        if server.returncode != 0:
            errors.append(f"`{_command_text(server)}` failed: {server.stderr or server.stdout}")
    except LocalModelBridgeError as exc:
        errors.append(str(exc))

    try:
        ps = _run_lms(["ps", "--json"], lms_path=executable, runner=runner)
        if ps.returncode == 0:
            loaded_models = _parse_loaded_models(ps.stdout)
        else:
            errors.append(f"`{_command_text(ps)}` failed: {ps.stderr or ps.stdout}")
    except LocalModelBridgeError as exc:
        errors.append(str(exc))

    return {
        "available": True,
        "path": executable,
        "server_status": server_status,
        "status_output": status_output,
        "loaded_models": loaded_models,
        "errors": errors,
        "supports_context_reload": True,
    }


def _observed_by_model(config: DoctorConfig) -> dict[str, ObservedModel]:
    return {model.model_id: model for model in config.observed_models}


def _registry_role_by_model(config: DoctorConfig) -> dict[str, str]:
    role_by_model = {model.model_id: model.role_classification for model in config.registry_models}
    role_by_model.update({model.model_id: model.role_classification for model in config.observed_models})
    return role_by_model


def _loaded_context_by_alias(loaded_models: list[dict[str, Any]]) -> dict[str, int]:
    contexts: dict[str, int] = {}
    for model in loaded_models:
        context = model.get("contextLength") or model.get("context_length") or model.get("context_window")
        if isinstance(context, bool):
            continue
        if isinstance(context, (int, float)) and int(context) > 0:
            for alias in loaded_model_aliases(model):
                contexts[alias] = int(context)
    return contexts


def _loaded_max_context_by_alias(loaded_models: list[dict[str, Any]]) -> dict[str, int]:
    contexts: dict[str, int] = {}
    for model in loaded_models:
        context = model.get("maxContextLength") or model.get("max_context_length")
        if isinstance(context, bool):
            continue
        if isinstance(context, (int, float)) and int(context) > 0:
            for alias in loaded_model_aliases(model):
                contexts[alias] = int(context)
    return contexts


def _loaded_model_ids(loaded_models: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for model in loaded_models:
        identifier = model.get("identifier") or model.get("modelKey") or model.get("displayName")
        if isinstance(identifier, str) and identifier and identifier not in ids:
            ids.append(identifier)
    return ids


def _loaded_model_size_bytes(model: dict[str, Any]) -> int | None:
    value = model.get("sizeBytes") or model.get("size_bytes")
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and int(value) > 0:
        return int(value)
    return None


def _format_gib(value: int | None) -> str:
    if value is None:
        return "unknown"
    return f"{value / 1024**3:.2f} GiB"


def build_loaded_resource_report(loaded_models: list[dict[str, Any]]) -> dict[str, Any]:
    sizes = [_loaded_model_size_bytes(model) for model in loaded_models]
    known_sizes = [size for size in sizes if size is not None]
    total_size = sum(known_sizes) if known_sizes else None
    count = len(loaded_models)
    warning_active = count >= LOADED_MODEL_COUNT_WARNING_THRESHOLD or (
        total_size is not None and total_size >= LOADED_MODEL_SIZE_WARNING_THRESHOLD_BYTES
    )
    return {
        "loaded_model_count": count,
        "loaded_model_ids": _loaded_model_ids(loaded_models),
        "known_size_count": len(known_sizes),
        "total_loaded_size_bytes": total_size,
        "warning_active": warning_active,
    }


def _best_context(
    model_id: str,
    endpoint_context: int | None,
    loaded_context_by_alias: dict[str, int],
    observed: ObservedModel | None,
) -> tuple[int | None, str]:
    if endpoint_context is not None:
        return endpoint_context, "endpoint"
    loaded_context = loaded_context_by_alias.get(model_id)
    if loaded_context is not None:
        return loaded_context, "lms_cli"
    if observed and observed.human_observed_context_window is not None:
        return observed.human_observed_context_window, "registry_observed"
    return None, "unknown"


def build_model_operations_status_report(
    config: DoctorConfig | None = None,
    *,
    requester: JSONRequester = request_json,
    lms_path: str | None = None,
    runner: CommandRunner = run_local_command,
) -> dict[str, Any]:
    loaded_config = config or load_doctor_config()
    endpoint = check_endpoint(loaded_config, requester)
    control = inspect_lms_control(lms_path=lms_path, runner=runner)
    observed_by_model = _observed_by_model(loaded_config)
    role_by_model = _registry_role_by_model(loaded_config)
    loaded_contexts = _loaded_context_by_alias(control["loaded_models"])
    loaded_max_contexts = _loaded_max_context_by_alias(control["loaded_models"])

    visible_models: list[dict[str, Any]] = []
    if endpoint["reachable"]:
        for model in endpoint["models"]:
            observed = observed_by_model.get(model.model_id)
            context, context_source = _best_context(
                model.model_id,
                model.context_window,
                loaded_contexts,
                observed,
            )
            visible_models.append(
                {
                    "model_id": model.model_id,
                    "context_window": context,
                    "context_source": context_source,
                    "endpoint_context_window": model.context_window,
                    "registry_observed_context_window": (
                        observed.human_observed_context_window if observed else None
                    ),
                    "max_context_window": loaded_max_contexts.get(model.model_id),
                    "role_classification": role_by_model.get(model.model_id, "unclassified local model"),
                    "warnings": model_warnings(
                        context,
                        observed.human_observed_context_window if observed else None,
                        loaded_config.low_context_window_threshold,
                    ),
                }
            )

    return {
        "endpoint": loaded_config.endpoint,
        "endpoint_reachable": endpoint["reachable"],
        "endpoint_error": endpoint["error"],
        "visible_models": visible_models,
        "lms_control": control,
        "loaded_resource_report": build_loaded_resource_report(control["loaded_models"]),
        "coder_retest": build_coder_retest_recommendation(
            config=loaded_config,
            loaded_context_by_alias=loaded_contexts,
            loaded_max_context_by_alias=loaded_max_contexts,
        ),
        "human_judgment_required": True,
    }


def build_coder_retest_recommendation(
    *,
    config: DoctorConfig | None = None,
    loaded_context_by_alias: dict[str, int] | None = None,
    loaded_max_context_by_alias: dict[str, int] | None = None,
) -> dict[str, Any]:
    loaded_config = config or load_doctor_config()
    observed = _observed_by_model(loaded_config).get(CODER_14B_MODEL_ID)
    loaded_contexts = loaded_context_by_alias or {}
    loaded_max_contexts = loaded_max_context_by_alias or {}
    live_context = loaded_contexts.get(CODER_14B_MODEL_ID)
    max_context = loaded_max_contexts.get(CODER_14B_MODEL_ID)
    next_context = FIRST_RETEST_CONTEXT
    if live_context and live_context >= FIRST_RETEST_CONTEXT:
        next_context = 8192 if live_context < 8192 else live_context

    return {
        "model_id": CODER_14B_MODEL_ID,
        "previous_bridge_status": "callable bridge verified; usefulness pending retest",
        "previous_latency_seconds": 20.199,
        "previous_context_window": observed.human_observed_context_window if observed else 2048,
        "previous_quality_note": "coherent but shallow; misunderstood routing-test work as gameplay",
        "likely_issue": "The weak first result may have been caused by low context, not model capability alone.",
        "live_context_window": live_context,
        "max_context_window": max_context,
        "recommended_first_retest_context": FIRST_RETEST_CONTEXT,
        "next_retest_context": next_context,
        "secondary_retest_context": 8192,
        "fallback": (
            "If higher context is too slow, classify Coder-14B as deep consult only or "
            "test qwen2.5-3b-instruct as a faster temporary Engineering triage model."
        ),
        "current_context_guidance": current_context_guidance(live_context),
        "routine_first_officer_use": "Do not use Coder-14B for routine First Officer chatter until latency/usefulness are verified.",
    }


def current_context_guidance(live_context: int | None) -> str:
    if live_context is None:
        return "Live context is unknown; inspect LM Studio status before deciding whether a reload is needed."
    if live_context >= 8192:
        return (
            "Live context is already high enough for the higher-context retest; run readiness at the current "
            "context before attempting any reload."
        )
    if live_context >= FIRST_RETEST_CONTEXT:
        return "Live context is above the first retest target; run readiness before considering 8192."
    return "Live context is below the first retest target; prepare 4096 before any authorized reload."


def format_model_operations_status(report: dict[str, Any]) -> str:
    lines = [
        "Starship Model Operations - Local Model Status",
        f"Endpoint: {report['endpoint']}",
        f"Endpoint reachable: {'yes' if report['endpoint_reachable'] else 'no'}",
        "Human judgment required: yes",
    ]
    if not report["endpoint_reachable"]:
        lines.append(f"Endpoint error: {report['endpoint_error']}")
        lines.append("Likely causes:")
        lines.extend(f"- {cause}" for cause in LIKELY_UNREACHABLE_CAUSES)

    control = report["lms_control"]
    lines.extend(
        [
            f"LM Studio control path available: {'yes' if control['available'] else 'no'}",
            f"Control path: {control['path'] or 'not found'}",
            f"Server status: {control['server_status']}",
            f"Runtime context reload support: {'yes' if control['supports_context_reload'] else 'no'}",
        ]
    )
    if control["errors"]:
        lines.append("Control warnings:")
        lines.extend(f"- {error}" for error in control["errors"])

    lines.append("Visible models from local endpoint:")
    if report["visible_models"]:
        for model in report["visible_models"]:
            lines.append(
                f"- {model['model_id']} | context_window: {format_context(model['context_window'])} "
                f"({model['context_source']}) | registry_observed_context_window: "
                f"{format_context(model['registry_observed_context_window'])} | role: {model['role_classification']}"
            )
            if model["max_context_window"] is not None:
                lines.append(f"  max_context_window: {model['max_context_window']}")
            for warning in model["warnings"]:
                lines.append(f"  warning: {warning}")
    else:
        lines.append("- None visible through the configured endpoint.")

    lines.append("Loaded models from LM Studio CLI:")
    if control["loaded_models"]:
        for loaded in control["loaded_models"]:
            identifier = loaded.get("identifier") or loaded.get("modelKey") or loaded.get("displayName") or "unknown"
            model_key = loaded.get("modelKey") or "unknown"
            context = loaded.get("contextLength") or loaded.get("context_length") or loaded.get("context_window")
            max_context = loaded.get("maxContextLength") or loaded.get("max_context_length")
            status = loaded.get("status") or "unknown"
            lines.append(
                f"- {identifier} | model_key: {model_key} | context_window: {format_context(context)} | "
                f"max_context_window: {format_context(max_context)} | status: {status}"
            )
    else:
        lines.append("- None reported by lms ps --json.")

    lines.extend(format_loaded_resource_report(report["loaded_resource_report"]))
    lines.extend(format_coder_retest_recommendation(report["coder_retest"]))
    return "\n".join(lines)


def format_loaded_resource_report(report: dict[str, Any]) -> list[str]:
    lines = [
        "Loaded resource state:",
        f"- Loaded model count: {report['loaded_model_count']}",
        f"- Known loaded model size total: {_format_gib(report['total_loaded_size_bytes'])}",
    ]
    if report["loaded_model_ids"]:
        lines.append(f"- Loaded model ids: {', '.join(report['loaded_model_ids'])}")
    else:
        lines.append("- Loaded model ids: none")
    if report["warning_active"]:
        lines.extend(
            [
                "- Warning: multiple large local models are currently loaded.",
                "- Future readiness comparisons may be slower or resource-sensitive.",
                "- Starship will not eject or unload models without Captain authorization.",
            ]
        )
    return lines


def format_coder_retest_recommendation(recommendation: dict[str, Any]) -> list[str]:
    return [
        "Coder-14B higher-context retest recommendation:",
        f"- Model: {recommendation['model_id']}",
        f"- Previous bridge status: {recommendation['previous_bridge_status']}",
        f"- Previous latency: {format_latency(recommendation['previous_latency_seconds'])}",
        f"- Previous observed context_window: {recommendation['previous_context_window']}",
        f"- Previous quality note: {recommendation['previous_quality_note']}",
        f"- Live context_window: {format_context(recommendation['live_context_window'])}",
        f"- Max context_window: {format_context(recommendation['max_context_window'])}",
        f"- Recommendation: retest at {recommendation['recommended_first_retest_context']} first; use 8192 only if practical.",
        f"- Current context guidance: {recommendation['current_context_guidance']}",
        f"- Fallback: {recommendation['fallback']}",
        f"- Boundary: {recommendation['routine_first_officer_use']}",
    ]


def build_model_operations_readiness_output(
    *,
    requester: JSONRequester = request_json,
    lms_path: str | None = None,
    runner: CommandRunner = run_local_command,
) -> str:
    try:
        config = load_doctor_config()
        report = build_readiness_report(config, requester=requester)
        control = inspect_lms_control(lms_path=lms_path, runner=runner)
        merge_lms_context_into_readiness_report(report, config, control["loaded_models"])
        output = format_readiness_report(report).replace(
            "Starship Local Model Server Doctor - Readiness Report",
            "Starship Model Operations - Readiness Report",
            1,
        )
        resource_report = build_loaded_resource_report(control["loaded_models"])
        return "\n".join([output, *format_loaded_resource_report(resource_report)])
    except LocalModelBridgeError as exc:
        return "\n".join(
            [
                "Starship Model Operations - Readiness Report",
                "Endpoint reachable: no",
                f"Error: {exc}",
                "Likely causes:",
                *[f"- {cause}" for cause in LIKELY_UNREACHABLE_CAUSES],
            ]
        )


def merge_lms_context_into_readiness_report(
    report: dict[str, Any],
    config: DoctorConfig,
    loaded_models: list[dict[str, Any]],
) -> None:
    loaded_contexts = _loaded_context_by_alias(loaded_models)
    observed_by_model = _observed_by_model(config)
    for model in report.get("models_visible", []):
        if not isinstance(model, dict):
            continue
        model_id = model.get("model_id")
        if not isinstance(model_id, str):
            continue
        if model.get("context_window") is None and model_id in loaded_contexts:
            model["context_window"] = loaded_contexts[model_id]
        if model.get("context_window") is not None:
            observed = observed_by_model.get(model_id)
            model["warnings"] = merge_context_warnings(
                model.get("warnings", []),
                model["context_window"],
                observed.human_observed_context_window if observed else model.get("human_observed_context_window"),
                config.low_context_window_threshold,
            )
    for result in report.get("models_tested", []):
        if not isinstance(result, dict):
            continue
        model_id = result.get("model_id")
        if not isinstance(model_id, str):
            continue
        if result.get("context_window") is None and model_id in loaded_contexts:
            result["context_window"] = loaded_contexts[model_id]
        if result.get("context_window") is not None:
            observed = observed_by_model.get(model_id)
            result["warnings"] = merge_context_warnings(
                result.get("warnings", []),
                result["context_window"],
                observed.human_observed_context_window if observed else result.get("human_observed_context_window"),
                config.low_context_window_threshold,
            )


def merge_context_warnings(
    existing_warnings: object,
    context_window: int | None,
    human_observed_context_window: int | None,
    threshold: int,
) -> list[str]:
    warnings = [warning for warning in merge_warning_lists(existing_warnings) if warning != CONTEXT_UNKNOWN_WARNING]
    return merge_warning_lists(warnings, model_warnings(context_window, human_observed_context_window, threshold))


def merge_warning_lists(*warning_lists: object) -> list[str]:
    merged: list[str] = []
    for warnings in warning_lists:
        if not isinstance(warnings, list):
            continue
        for warning in warnings:
            if isinstance(warning, str) and warning not in merged:
                merged.append(warning)
    return merged


def build_model_operations_status_output(
    *,
    requester: JSONRequester = request_json,
    lms_path: str | None = None,
    runner: CommandRunner = run_local_command,
) -> str:
    try:
        config = load_doctor_config()
        return format_model_operations_status(
            build_model_operations_status_report(
                config,
                requester=requester,
                lms_path=lms_path,
                runner=runner,
            )
        )
    except LocalModelBridgeError as exc:
        return "\n".join(
            [
                "Starship Model Operations - Local Model Status",
                "Endpoint reachable: no",
                f"Error: {exc}",
                "Likely causes:",
                *[f"- {cause}" for cause in LIKELY_UNREACHABLE_CAUSES],
            ]
        )


def prepare_coder_retest_output(
    *,
    target_context: int = FIRST_RETEST_CONTEXT,
    lms_path: str | None = None,
    runner: CommandRunner = run_local_command,
) -> str:
    if target_context not in SUPPORTED_RETEST_CONTEXTS:
        return f"Starship Model Operations - Coder-14B Retest Preparation\nRefused unsupported target context: {target_context}"

    lines = [
        "Starship Model Operations - Coder-14B Retest Preparation",
        f"Model: {CODER_14B_MODEL_ID}",
        f"Target context_window: {target_context}",
        "Runtime state changed: no",
        "Captain authorization required before any load/reload action.",
        "Risk note: higher context can slow responses, increase memory use, or fail to load.",
    ]

    control = inspect_lms_control(lms_path=lms_path, runner=runner)
    if not control["available"]:
        lines.extend(
            [
                "LM Studio control path available: no",
                "Starship can inspect and test models, but cannot yet control LM Studio loading on this installation.",
            ]
        )
        return "\n".join(lines)

    current_context = _loaded_context_by_alias(control["loaded_models"]).get(CODER_14B_MODEL_ID)
    lines.append(f"Current live context_window: {format_context(current_context)}")
    if current_context is not None and current_context >= target_context:
        lines.append(
            "No reload estimate needed: current live context is already at or above the requested target. "
            "Run readiness at the current context instead of lowering context for this retest."
        )
        return "\n".join(lines)

    try:
        estimate = _run_lms(
            [
                "load",
                CODER_14B_MODEL_ID,
                "--context-length",
                str(target_context),
                "--identifier",
                CODER_14B_MODEL_ID,
                "--estimate-only",
                "--yes",
            ],
            lms_path=lms_path,
            runner=runner,
            timeout_seconds=60,
        )
    except LocalModelBridgeError as exc:
        lines.extend(
            [
                "LM Studio control path available: no",
                f"Estimate failed: {exc}",
                "Starship can inspect and test models, but cannot yet control LM Studio loading on this installation.",
            ]
        )
        return "\n".join(lines)

    lines.append("LM Studio estimate command completed.")
    lines.append(f"Command: {_command_text(estimate)}")
    lines.append(f"Exit code: {estimate.returncode}")
    if estimate.stdout:
        lines.append("Estimate output:")
        lines.append(estimate.stdout)
    if estimate.stderr:
        lines.append("Estimate warnings:")
        lines.append(estimate.stderr)
    if estimate.returncode != 0:
        lines.append("Reload should not proceed until the estimate succeeds.")
    else:
        lines.append("Next action: Captain may authorize reload at this context from the GUI.")
    return "\n".join(lines)


def authorized_coder_context_reload_output(
    *,
    target_context: int,
    captain_authorized: bool,
    requester: JSONRequester = request_json,
    lms_path: str | None = None,
    runner: CommandRunner = run_local_command,
) -> str:
    lines = [
        "Starship Model Operations - Authorized Coder-14B Context Reload",
        f"Model: {CODER_14B_MODEL_ID}",
        f"Target context_window: {target_context}",
        "Runtime action: LM Studio model load/reload request",
        "Expected risk: slower response, higher memory use, or load failure.",
    ]
    if target_context not in SUPPORTED_RETEST_CONTEXTS:
        lines.append(f"Refused unsupported target context: {target_context}")
        return "\n".join(lines)
    if not captain_authorized:
        lines.append("Refused: Captain authorization is required before changing LM Studio runtime state.")
        return "\n".join(lines)

    control = inspect_lms_control(lms_path=lms_path, runner=runner)
    if not control["available"]:
        lines.extend(
            [
                "LM Studio control path available: no",
                "Starship can inspect and test models, but cannot yet control LM Studio loading on this installation.",
            ]
        )
        return "\n".join(lines)
    current_context = _loaded_context_by_alias(control["loaded_models"]).get(CODER_14B_MODEL_ID)
    lines.append(f"Current live context_window: {format_context(current_context)}")
    if current_context is not None and current_context >= target_context:
        lines.append(
            "Refused: current live context is already at or above the requested target, so this would not be "
            "a higher-context retest. Run readiness at the current context instead."
        )
        return "\n".join(lines)

    try:
        estimate = _run_lms(
            [
                "load",
                CODER_14B_MODEL_ID,
                "--context-length",
                str(target_context),
                "--identifier",
                CODER_14B_MODEL_ID,
                "--estimate-only",
                "--yes",
            ],
            lms_path=lms_path,
            runner=runner,
            timeout_seconds=60,
        )
    except LocalModelBridgeError as exc:
        lines.extend(
            [
                f"Estimate failed: {exc}",
                "Starship can inspect and test models, but cannot yet control LM Studio loading on this installation.",
            ]
        )
        return "\n".join(lines)

    lines.append(f"Estimate command exit code: {estimate.returncode}")
    if estimate.stdout:
        lines.append("Estimate output:")
        lines.append(estimate.stdout)
    if estimate.stderr:
        lines.append("Estimate warnings:")
        lines.append(estimate.stderr)
    if estimate.returncode != 0:
        lines.append("Reload refused because the estimate did not succeed.")
        return "\n".join(lines)

    try:
        reload_result = _run_lms(
            [
                "load",
                CODER_14B_MODEL_ID,
                "--context-length",
                str(target_context),
                "--identifier",
                CODER_14B_MODEL_ID,
                "--yes",
            ],
            lms_path=lms_path,
            runner=runner,
            timeout_seconds=180,
        )
    except LocalModelBridgeError as exc:
        lines.append(f"Reload failed: {exc}")
        return "\n".join(lines)

    lines.append(f"Reload command: {_command_text(reload_result)}")
    lines.append(f"Reload exit code: {reload_result.returncode}")
    if reload_result.stdout:
        lines.append("Reload output:")
        lines.append(reload_result.stdout)
    if reload_result.stderr:
        lines.append("Reload warnings:")
        lines.append(reload_result.stderr)
    if reload_result.returncode != 0:
        lines.append("Readiness was not rerun because reload failed.")
        return "\n".join(lines)

    lines.append("")
    lines.append("Readiness after authorized reload:")
    lines.append(build_model_operations_readiness_output(requester=requester, lms_path=lms_path, runner=runner))
    return "\n".join(lines)
