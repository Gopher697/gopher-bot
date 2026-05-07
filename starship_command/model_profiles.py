from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


BASE_DIR = Path(__file__).resolve().parent
MODEL_PROFILES_PATH = BASE_DIR / "model_profiles.yaml"

INFERENCE_PAYLOAD_FIELDS = ("temperature", "top_p", "top_k", "max_tokens", "stop", "response_format")
CONCRETE_PROFILE_FAILURE_WARNINGS = {
    "context_below_profile_target",
    "gpu_offload_zero",
    "thinking_mode_enabled_for_schema_test",
}
LIVE_CONTEXT_KEYS = (
    "contextLength",
    "context_length",
    "context_window",
    "loaded_context_length",
    "loaded_context_window",
    "n_ctx",
)
LIVE_GPU_OFFLOAD_KEYS = (
    "gpuOffload",
    "gpu_offload",
    "gpuOffloadRatio",
    "gpu_offload_ratio",
    "gpuLayers",
    "gpu_layers",
    "offloadedLayers",
    "offloaded_layers",
)
LIVE_THINKING_KEYS = (
    "thinking",
    "thinkingMode",
    "thinking_mode",
    "enableThinking",
    "enable_thinking",
    "reasoning",
    "reasoningMode",
    "reasoning_mode",
)


class ModelProfileError(RuntimeError):
    """Raised when model profile configuration cannot be used safely."""


@dataclass(frozen=True)
class ModelProfile:
    profile_id: str
    display_name: str
    intended_models: list[str]
    load_time: dict[str, Any]
    inference: dict[str, Any]
    runtime: dict[str, Any]


def load_model_profile_registry(path: Path = MODEL_PROFILES_PATH) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ModelProfileError("model_profiles.yaml must contain a mapping")
    profiles = raw.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise ModelProfileError("model_profiles.yaml must define profiles")
    for profile_id, profile in profiles.items():
        if not isinstance(profile_id, str) or not isinstance(profile, dict):
            raise ModelProfileError("Each model profile must be a mapping")
        for key in ("intended_models", "load_time", "inference", "runtime"):
            if key not in profile:
                raise ModelProfileError(f"Model profile {profile_id} must define {key}")
    return raw


def load_model_profiles(path: Path = MODEL_PROFILES_PATH) -> dict[str, ModelProfile]:
    registry = load_model_profile_registry(path)
    profiles: dict[str, ModelProfile] = {}
    for profile_id, raw_profile in registry["profiles"].items():
        intended = raw_profile.get("intended_models")
        if not isinstance(intended, list) or not all(isinstance(item, str) for item in intended):
            raise ModelProfileError(f"Model profile {profile_id} intended_models must be a string list")
        profiles[profile_id] = ModelProfile(
            profile_id=profile_id,
            display_name=str(raw_profile.get("display_name", profile_id)),
            intended_models=list(intended),
            load_time=dict(raw_profile.get("load_time") or {}),
            inference=dict(raw_profile.get("inference") or {}),
            runtime=dict(raw_profile.get("runtime") or {}),
        )
    return profiles


def get_model_profile(profile_id: str, path: Path = MODEL_PROFILES_PATH) -> ModelProfile | None:
    return load_model_profiles(path).get(profile_id)


def setting_control_summary(path: Path = MODEL_PROFILES_PATH) -> dict[str, str]:
    registry = load_model_profile_registry(path)
    raw = registry.get("setting_control", {})
    if not isinstance(raw, dict):
        return {}
    summary: dict[str, str] = {}
    for key, value in raw.items():
        if isinstance(key, str) and isinstance(value, dict) and isinstance(value.get("classification"), str):
            summary[key] = value["classification"]
    return summary


def model_observation(model_id: str, path: Path = MODEL_PROFILES_PATH) -> dict[str, Any] | None:
    registry = load_model_profile_registry(path)
    observations = registry.get("model_observations", {})
    if not isinstance(observations, dict):
        return None
    raw = observations.get(model_id)
    return raw if isinstance(raw, dict) else None


def context_target_for_model(profile: ModelProfile, model_id: str) -> int | None:
    per_model = profile.load_time.get("per_model_context_targets")
    if isinstance(per_model, dict):
        value = per_model.get(model_id)
        if isinstance(value, int) and value > 0:
            return value
    value = profile.load_time.get("context_target")
    return value if isinstance(value, int) and value > 0 else None


def inference_settings_for_profile(profile: ModelProfile) -> dict[str, Any]:
    settings: dict[str, Any] = {}
    for key in ("temperature", "top_p", "top_k", "max_tokens"):
        value = profile.inference.get(key)
        if value is not None:
            settings[key] = value
    stop_strings = profile.inference.get("stop_strings")
    if isinstance(stop_strings, list) and stop_strings:
        settings["stop"] = [item for item in stop_strings if isinstance(item, str)]
    return settings


def apply_profile_to_payload(payload: dict[str, Any], profile: ModelProfile | None) -> dict[str, Any]:
    if profile is None:
        return payload
    payload.update(inference_settings_for_profile(profile))
    structured_output = profile.inference.get("structured_output")
    if structured_output is True:
        payload["response_format"] = {"type": "json_object"}
    return payload


def inference_settings_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: payload[key] for key in INFERENCE_PAYLOAD_FIELDS if key in payload}


def _coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, float) and value > 0:
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        return parsed if parsed > 0 else None
    return None


def _coerce_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().casefold()
        if lowered in {"true", "yes", "on", "enabled"}:
            return True
        if lowered in {"false", "no", "off", "disabled"}:
            return False
    return None


def _live_value(raw_model: dict[str, Any] | None, keys: tuple[str, ...]) -> object:
    if not isinstance(raw_model, dict):
        return None
    for key in keys:
        if key in raw_model:
            return raw_model[key]
    return None


def live_context_window(raw_model: dict[str, Any] | None, fallback: int | None = None) -> int | None:
    return _coerce_int(_live_value(raw_model, LIVE_CONTEXT_KEYS)) or fallback


def live_gpu_offload(raw_model: dict[str, Any] | None) -> object:
    return _live_value(raw_model, LIVE_GPU_OFFLOAD_KEYS)


def live_thinking_mode(raw_model: dict[str, Any] | None) -> bool | None:
    return _coerce_bool(_live_value(raw_model, LIVE_THINKING_KEYS))


def _compliance(expected: object, live: object) -> str:
    if live is None:
        return "unknown"
    return "pass" if live == expected else "fail"


def build_profile_compliance(
    *,
    profile_id: str,
    model_id: str,
    live_model: dict[str, Any] | None = None,
    live_context: int | None = None,
    inference_settings_sent: dict[str, Any] | None = None,
    path: Path = MODEL_PROFILES_PATH,
) -> dict[str, Any]:
    profile = get_model_profile(profile_id, path)
    if profile is None:
        return {
            "profile_used": profile_id,
            "profile_found": False,
            "model_id": model_id,
            "warnings": ["profile_not_found"],
            "overall_compliance": "unknown",
            "manual_unknown_settings": ["context_length", "gpu_offload", "thinking_mode"],
            "inference_settings_sent": inference_settings_sent or {},
        }

    context_target = context_target_for_model(profile, model_id)
    context_live = live_context_window(live_model, live_context)
    if context_target is None or context_live is None:
        context_compliance = "unknown"
    else:
        context_compliance = "pass" if context_live >= context_target else "fail"

    warnings: list[str] = []
    if context_compliance == "fail":
        warnings.append("context_below_profile_target")

    gpu_policy = profile.load_time.get("gpu_offload_policy")
    gpu_live = live_gpu_offload(live_model)
    gpu_compliance = "unknown"
    if gpu_live in {0, 0.0, "0"}:
        gpu_compliance = "fail"
        warnings.append("gpu_offload_zero")

    thinking_target = profile.runtime.get("thinking_mode")
    thinking_live = live_thinking_mode(live_model)
    thinking_compliance = (
        _compliance(thinking_target, thinking_live) if isinstance(thinking_target, bool) else "unknown"
    )
    if thinking_compliance == "fail" and thinking_target is False:
        warnings.append("thinking_mode_enabled_for_schema_test")

    manual_unknown_settings: list[str] = []
    if gpu_live is None:
        manual_unknown_settings.append("gpu_offload")
    if thinking_live is None:
        manual_unknown_settings.append("thinking_mode")
    manual_unknown_settings.extend(["cpu_threads", "batch_size", "context_overflow_behavior"])

    observation = model_observation(model_id, path)
    profile_notes: list[str] = []
    retest_required = False
    observed_settings: dict[str, Any] = {}
    if observation:
        observed_settings = dict(observation.get("observed_settings") or {})
        status = observation.get("status")
        if isinstance(status, str):
            profile_notes.append(status)
            if status == "settings_suspect_retest_required":
                retest_required = True
        interpretation = observation.get("interpretation")
        if isinstance(interpretation, str):
            profile_notes.append(interpretation)

    if any(warning in CONCRETE_PROFILE_FAILURE_WARNINGS for warning in warnings):
        overall = "fail"
    elif context_compliance == "pass" and not warnings:
        overall = "pass" if not manual_unknown_settings else "unknown"
    else:
        overall = "unknown"

    return {
        "profile_used": profile.profile_id,
        "profile_found": True,
        "model_id": model_id,
        "model_in_profile": model_id in profile.intended_models,
        "context_target": context_target,
        "live_context": context_live,
        "context_compliance": context_compliance,
        "gpu_offload_target_policy": gpu_policy,
        "live_gpu_offload": gpu_live,
        "gpu_offload_compliance": gpu_compliance,
        "thinking_mode_target": thinking_target,
        "live_thinking_mode": thinking_live,
        "thinking_mode_compliance": thinking_compliance,
        "inference_settings_sent": inference_settings_sent or {},
        "manual_unknown_settings": sorted(dict.fromkeys(manual_unknown_settings)),
        "warnings": sorted(dict.fromkeys(warnings)),
        "overall_compliance": overall,
        "profile_notes": profile_notes,
        "observed_settings": observed_settings,
        "retest_required": retest_required,
        "captain_authorization_required_for_runtime_changes": bool(
            profile.load_time.get("captain_authorization_required_for_runtime_changes", True)
        ),
    }


def profile_compliance_fails(compliance: dict[str, Any]) -> bool:
    return compliance.get("overall_compliance") == "fail" or any(
        warning in CONCRETE_PROFILE_FAILURE_WARNINGS
        for warning in compliance.get("warnings", [])
        if isinstance(warning, str)
    )


def apply_profile_compliance_to_result(result: dict[str, Any], compliance: dict[str, Any]) -> None:
    result["model_profile_compliance"] = compliance
    stale_profile_warnings = {*CONCRETE_PROFILE_FAILURE_WARNINGS, "model_settings_not_profile_compliant"}
    warnings = [
        warning
        for warning in result.get("warnings", [])
        if isinstance(warning, str) and warning not in stale_profile_warnings
    ]
    warnings.extend(item for item in compliance.get("warnings", []) if isinstance(item, str))
    if profile_compliance_fails(compliance):
        warnings.append("model_settings_not_profile_compliant")
        result["trust_gate"] = "fail"
    result["warnings"] = sorted(dict.fromkeys(warnings))


def format_profile_value(value: object) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        return ", ".join(f"{key}={value[key]}" for key in sorted(value)) or "none"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) or "none"
    return str(value)


def format_profile_compliance_lines(compliance: dict[str, Any], indent: str = "  ") -> list[str]:
    settings = compliance.get("inference_settings_sent", {})
    manual_unknown = compliance.get("manual_unknown_settings", [])
    warnings = compliance.get("warnings", [])
    lines = [
        f"{indent}Model Profile:",
        f"{indent}- Profile used: {format_profile_value(compliance.get('profile_used'))}",
        f"{indent}- Model id: {format_profile_value(compliance.get('model_id'))}",
        f"{indent}- Context target: {format_profile_value(compliance.get('context_target'))}",
        f"{indent}- Live context: {format_profile_value(compliance.get('live_context'))}",
        f"{indent}- Context compliance: {format_profile_value(compliance.get('context_compliance'))}",
        f"{indent}- GPU offload policy: {format_profile_value(compliance.get('gpu_offload_target_policy'))}",
        f"{indent}- Live GPU offload: {format_profile_value(compliance.get('live_gpu_offload'))}",
        f"{indent}- GPU offload compliance: {format_profile_value(compliance.get('gpu_offload_compliance'))}",
        f"{indent}- Thinking mode target: {format_profile_value(compliance.get('thinking_mode_target'))}",
        f"{indent}- Live thinking mode: {format_profile_value(compliance.get('live_thinking_mode'))}",
        f"{indent}- Thinking mode compliance: {format_profile_value(compliance.get('thinking_mode_compliance'))}",
        f"{indent}- Inference settings sent by Starship: {format_profile_value(settings)}",
        f"{indent}- Manual/unknown settings: {format_profile_value(manual_unknown)}",
        f"{indent}- Profile warnings: {format_profile_value(warnings)}",
        f"{indent}- Profile compliance: {format_profile_value(compliance.get('overall_compliance'))}",
    ]
    if compliance.get("retest_required"):
        lines.append(f"{indent}- Retest required: yes")
    for note in compliance.get("profile_notes", []):
        lines.append(f"{indent}- Profile note: {note}")
    return lines
