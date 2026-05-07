from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from starship_command import model_operations
from starship_command.local_model_adapter import LocalModelBridgeError
from starship_command.local_model_server_doctor import DoctorConfig, ObservedModel, ReadinessTest, validate_doctor_endpoint
from starship_command.model_operations import (
    CODER_14B_MODEL_ID,
    CONTEXT_UNKNOWN_WARNING,
    LocalCommandResult,
    authorized_coder_context_reload_output,
    build_coder_retest_recommendation,
    build_model_operations_status_report,
    build_profile_compliance_output,
    build_profile_load_estimate_output,
    format_model_operations_status,
    prepare_coder_retest_output,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "starship_command" / "command_registry.yaml"
README_PATH = ROOT / "starship_command" / "README.md"
DOCTRINE = (
    "Codex and Starship Command are Engineering. The Captain approves, judges, and authorizes. "
    "Codex inspects, implements, tests, and reports. The user is never the integration layer."
)


def doctor_config() -> DoctorConfig:
    observed = [
        ObservedModel("qwen/qwen3.5-9b", "qwen_qwen3_5_9b", "fast triage candidate", 8192),
        ObservedModel(CODER_14B_MODEL_ID, "qwen2_5_coder_14b_instruct", "deep Engineering consult candidate", 2048),
    ]
    return DoctorConfig(
        endpoint="http://localhost:1234/v1",
        timeout_seconds=30,
        list_models_path="/models",
        chat_completions_path="/chat/completions",
        allow_non_local_endpoint=False,
        low_context_window_threshold=2048,
        temperature=0.1,
        max_tokens=300,
        registry_models=observed,
        observed_models=observed,
        readiness_tests=[
            ReadinessTest(
                model_id=CODER_14B_MODEL_ID,
                prompt_name="engineering_unit_test",
                prompt="Suggest one routing unit test.",
                system_prompt="You are an Engineering review assistant.",
                role_classification="deep Engineering consult candidate",
                max_tokens=160,
            )
        ],
    )


def test_model_operations_status_uses_live_lms_context_before_registry_fallback() -> None:
    def fake_request(method: str, url: str, payload: dict | None, timeout: float) -> dict:
        return {"data": [{"id": CODER_14B_MODEL_ID}]}

    def json_runner(command: list[str], timeout: float) -> LocalCommandResult:
        if command[-1] == "--json":
            return LocalCommandResult(
                command,
                0,
                (
                    '[{"identifier":"qwen2.5-coder-14b-instruct",'
                    '"modelKey":"qwen2.5-coder-14b-instruct",'
                    '"contextLength":16384,"maxContextLength":131072,"status":"idle"}]'
                ),
                "",
            )
        if command[1:3] == ["server", "status"]:
            return LocalCommandResult(command, 0, "The server is running on port 1234.", "")
        return LocalCommandResult(command, 0, "Server: ON (port: 1234)", "")

    report = build_model_operations_status_report(
        doctor_config(),
        requester=fake_request,
        lms_path="lms",
        runner=json_runner,
    )
    output = format_model_operations_status(report)

    assert "context_window: 16384 (lms_cli)" in output
    assert "registry_observed_context_window: 2048" in output
    assert "Previous latency: 20.199s" in output
    assert "retest at 4096 first" in output
    assert "LM Studio control path available: yes" in output


def test_model_operations_readiness_output_keeps_validation_summary(monkeypatch) -> None:
    def fake_report(config, requester=model_operations.request_json):
        return {
            "endpoint": "http://localhost:1234/v1",
            "endpoint_reachable": True,
            "models_visible": [],
            "registry_models_visible": [],
            "user_observed_models_missing": [],
            "models_tested": [
                {
                    "model_id": CODER_14B_MODEL_ID,
                    "prompt_name": "engineering_test_design",
                    "prompt_profile": "engineering_test_design",
                    "role_classification": "deep Engineering consult candidate",
                    "latency_seconds": 1.0,
                    "response_preview": "Test intent: Verify routing.",
                    "error": "",
                    "context_window": None,
                    "human_observed_context_window": None,
                    "schema_valid": False,
                    "division_vocabulary_valid": "not_applicable",
                    "warnings": ["missing_required_field"],
                    "missing_required_fields": ["Assertions", "Notes"],
                    "invalid_divisions": [],
                    "trust_gate": "fail",
                    "human_review_required": True,
                }
            ],
            "failures": [],
            "human_judgment_required": True,
        }

    monkeypatch.setattr(model_operations, "build_readiness_report", fake_report)
    monkeypatch.setattr(model_operations, "inspect_lms_control", lambda **kwargs: {"loaded_models": []})

    output = model_operations.build_model_operations_readiness_output()

    assert "Starship Model Operations - Readiness Report" in output
    assert "Schema: fail" in output
    assert "Warnings: missing_required_field" in output
    assert "Trust gate: fail" in output


def test_model_operations_context_merge_preserves_validation_warning_codes() -> None:
    report = {
        "models_visible": [],
        "models_tested": [
                {
                    "model_id": CODER_14B_MODEL_ID,
                    "prompt_profile": "engineering_test_design",
                    "context_window": None,
                "human_observed_context_window": None,
                "warnings": [CONTEXT_UNKNOWN_WARNING, "invented_structure_possible"],
                "schema_valid": True,
                "division_vocabulary_valid": "not_applicable",
                "missing_required_fields": [],
                "invalid_divisions": [],
                "trust_gate": "fail",
                "human_review_required": True,
            }
        ],
    }
    loaded_models = [
        {
            "identifier": CODER_14B_MODEL_ID,
            "modelKey": CODER_14B_MODEL_ID,
            "contextLength": 16384,
        }
    ]

    model_operations.merge_lms_context_into_readiness_report(report, doctor_config(), loaded_models)

    result = report["models_tested"][0]
    assert result["context_window"] == 16384
    assert "invented_structure_possible" in result["warnings"]
    assert CONTEXT_UNKNOWN_WARNING not in result["warnings"]
    assert result["model_profile_compliance"]["live_context"] == 16384
    assert result["model_profile_compliance"]["context_compliance"] == "pass"
    assert result["schema_valid"] is True
    assert result["trust_gate"] == "fail"


def test_model_operations_context_merge_keeps_unknown_warning_when_live_context_missing() -> None:
    report = {
        "models_visible": [],
        "models_tested": [
            {
                "model_id": CODER_14B_MODEL_ID,
                "context_window": None,
                "human_observed_context_window": None,
                "warnings": [CONTEXT_UNKNOWN_WARNING],
                "schema_valid": True,
                "division_vocabulary_valid": "not_applicable",
                "missing_required_fields": [],
                "invalid_divisions": [],
                "trust_gate": "human_review_required",
                "human_review_required": True,
            }
        ],
    }

    model_operations.merge_lms_context_into_readiness_report(report, doctor_config(), [])

    result = report["models_tested"][0]
    assert result["context_window"] is None
    assert CONTEXT_UNKNOWN_WARNING in result["warnings"]


def test_model_operations_context_merge_prefers_live_lms_context_for_profile_compliance() -> None:
    report = {
        "models_visible": [],
        "models_tested": [
            {
                "model_id": "qwen/qwen3.5-9b",
                "prompt_profile": "first_officer_triage",
                "context_window": 2048,
                "human_observed_context_window": None,
                "warnings": ["low programmatic context window (2048); likely quality limitation for code/project reasoning"],
                "schema_valid": True,
                "division_vocabulary_valid": "yes",
                "missing_required_fields": [],
                "invalid_divisions": [],
                "trust_gate": "human_review_required",
                "human_review_required": True,
            }
        ],
    }
    loaded_models = [
        {
            "identifier": "qwen/qwen3.5-9b",
            "modelKey": "qwen/qwen3.5-9b",
            "contextLength": 8192,
        }
    ]

    model_operations.merge_lms_context_into_readiness_report(report, doctor_config(), loaded_models)

    result = report["models_tested"][0]
    assert result["context_window"] == 8192
    assert result["model_profile_compliance"]["context_compliance"] == "pass"
    assert not any("low programmatic context window" in warning for warning in result["warnings"])


def test_model_operations_readiness_output_shows_live_context_without_stale_unknown_warning(monkeypatch) -> None:
    def fake_report(config, requester=model_operations.request_json):
        return {
            "endpoint": "http://localhost:1234/v1",
            "endpoint_reachable": True,
            "models_visible": [],
            "registry_models_visible": [],
            "user_observed_models_missing": [],
            "models_tested": [
                {
                    "model_id": CODER_14B_MODEL_ID,
                    "prompt_name": "engineering_test_design",
                    "prompt_profile": "engineering_test_design",
                    "role_classification": "deep Engineering consult candidate",
                    "latency_seconds": 1.0,
                    "response_preview": "Test intent: Verify routing.",
                    "error": "",
                    "context_window": None,
                    "human_observed_context_window": None,
                    "schema_valid": True,
                    "division_vocabulary_valid": "not_applicable",
                    "warnings": [CONTEXT_UNKNOWN_WARNING],
                    "missing_required_fields": [],
                    "invalid_divisions": [],
                    "trust_gate": "human_review_required",
                    "human_review_required": True,
                }
            ],
            "failures": [],
            "human_judgment_required": True,
        }

    monkeypatch.setattr(model_operations, "build_readiness_report", fake_report)
    monkeypatch.setattr(
        model_operations,
        "inspect_lms_control",
        lambda **kwargs: {
            "loaded_models": [
                {
                    "identifier": CODER_14B_MODEL_ID,
                    "modelKey": CODER_14B_MODEL_ID,
                    "contextLength": 16384,
                }
            ]
        },
    )

    output = model_operations.build_model_operations_readiness_output()

    assert "context_window: 16384" in output
    assert CONTEXT_UNKNOWN_WARNING not in output


def test_model_operations_status_warns_when_many_large_models_loaded() -> None:
    loaded_models = []
    for index in range(6):
        loaded_models.append(
            {
                "identifier": f"large-model-{index}",
                "modelKey": f"large/model-{index}",
                "contextLength": 8192,
                "sizeBytes": 8 * 1024**3,
                "status": "idle",
            }
        )

    def fake_request(method: str, url: str, payload: dict | None, timeout: float) -> dict:
        return {"data": []}

    def fake_runner(command: list[str], timeout: float) -> LocalCommandResult:
        if command[-1] == "--json":
            return LocalCommandResult(command, 0, json.dumps(loaded_models), "")
        if command[1:3] == ["server", "status"]:
            return LocalCommandResult(command, 0, "The server is running on port 1234.", "")
        return LocalCommandResult(command, 0, "Server: ON (port: 1234)", "")

    report = build_model_operations_status_report(
        doctor_config(),
        requester=fake_request,
        lms_path="lms",
        runner=fake_runner,
    )
    output = format_model_operations_status(report)

    assert "Loaded resource state:" in output
    assert "Loaded model count: 6" in output
    assert "Known loaded model size total: 48.00 GiB" in output
    assert "multiple large local models are currently loaded" in output
    assert "will not eject or unload models without Captain authorization" in output


def test_profile_compliance_output_reports_controllability_and_warnings() -> None:
    def fake_runner(command: list[str], timeout: float) -> LocalCommandResult:
        if command[-1] == "--json":
            return LocalCommandResult(
                command,
                0,
                (
                    '[{"identifier":"google/gemma-4-26b-a4b",'
                    '"modelKey":"google/gemma-4-26b-a4b",'
                    '"contextLength":8192,"gpuOffload":0,"enableThinking":true}]'
                ),
                "",
            )
        if command[1:3] == ["server", "status"]:
            return LocalCommandResult(command, 0, "The server is running on port 1234.", "")
        return LocalCommandResult(command, 0, "Server: ON (port: 1234)", "")

    output = build_profile_compliance_output(
        model_id="google/gemma-4-26b-a4b",
        profile_id="first_officer_triage",
        lms_path="lms",
        runner=fake_runner,
    )

    assert "Profile Compliance" in output
    assert "Live context: 8192" in output
    assert "Profile warnings: gpu_offload_zero, thinking_mode_enabled_for_schema_test" in output
    assert "temperature: inference_payload_controlled" in output


def test_profile_load_estimate_uses_profile_context_without_runtime_change() -> None:
    calls = []

    def fake_runner(command: list[str], timeout: float) -> LocalCommandResult:
        calls.append(command)
        return LocalCommandResult(command, 0, "Estimated memory looks acceptable.", "")

    output = build_profile_load_estimate_output(
        model_id="google/gemma-4-26b-a4b",
        profile_id="first_officer_triage",
        lms_path="lms",
        runner=fake_runner,
    )

    assert "Runtime state changed: no" in output
    assert "Target context_window: 8192" in output
    assert "--estimate-only" in calls[0]
    assert "--context-length" in calls[0]
    assert "8192" in calls[0]


def test_coder_retest_recommendation_records_known_weak_first_result() -> None:
    recommendation = build_coder_retest_recommendation(config=doctor_config())

    assert recommendation["previous_latency_seconds"] == pytest.approx(20.199)
    assert recommendation["previous_context_window"] == 2048
    assert recommendation["recommended_first_retest_context"] == 4096
    assert recommendation["secondary_retest_context"] == 8192
    assert "misunderstood" in recommendation["previous_quality_note"]
    assert "qwen2.5-3b-instruct" in recommendation["fallback"]


def test_model_operations_refuses_non_local_endpoint_in_registry() -> None:
    with pytest.raises(LocalModelBridgeError, match="external API endpoints are refused"):
        validate_doctor_endpoint("http://example.com/v1")


def test_prepare_coder_retest_uses_estimate_only_and_changes_no_runtime_state() -> None:
    calls = []

    def fake_runner(command: list[str], timeout: float) -> LocalCommandResult:
        calls.append(command)
        return LocalCommandResult(command, 0, "Estimated memory looks acceptable.", "")

    output = prepare_coder_retest_output(target_context=4096, lms_path="lms", runner=fake_runner)

    assert "Runtime state changed: no" in output
    estimate_call = next(call for call in calls if "--estimate-only" in call)
    assert "--context-length" in estimate_call
    assert "4096" in estimate_call


def test_unauthorized_reload_refuses_without_running_lms() -> None:
    calls = []

    def fake_runner(command: list[str], timeout: float) -> LocalCommandResult:
        calls.append(command)
        return LocalCommandResult(command, 0, "", "")

    output = authorized_coder_context_reload_output(
        target_context=4096,
        captain_authorized=False,
        lms_path="lms",
        runner=fake_runner,
    )

    assert "Captain authorization is required" in output
    assert calls == []


def test_reload_fails_safely_when_lms_control_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(model_operations, "find_lms_executable", lambda: None)

    output = prepare_coder_retest_output(target_context=4096)

    assert "LM Studio control path available: no" in output
    assert "cannot yet control LM Studio loading" in output


def test_authorized_reload_estimates_loads_and_reruns_readiness() -> None:
    calls = []

    def fake_runner(command: list[str], timeout: float) -> LocalCommandResult:
        calls.append(command)
        return LocalCommandResult(command, 0, "ok", "")

    def fake_request(method: str, url: str, payload: dict | None, timeout: float) -> dict:
        if method == "GET":
            return {"data": [{"id": CODER_14B_MODEL_ID, "contextLength": 4096}]}
        return {"choices": [{"message": {"content": "A focused routing unit test proposal."}}]}

    output = authorized_coder_context_reload_output(
        target_context=4096,
        captain_authorized=True,
        requester=fake_request,
        lms_path="lms",
        runner=fake_runner,
    )

    load_calls = [call for call in calls if call[:2] == ["lms", "load"]]
    assert len(load_calls) == 2
    assert "--estimate-only" in load_calls[0]
    assert "--estimate-only" not in load_calls[1]
    assert "Reload exit code: 0" in output
    assert "Readiness after authorized reload:" in output
    assert "Starship Model Operations - Readiness Report" in output


def test_authorized_reload_refuses_to_lower_current_high_context() -> None:
    calls = []

    def fake_runner(command: list[str], timeout: float) -> LocalCommandResult:
        calls.append(command)
        if command[-1] == "--json":
            return LocalCommandResult(
                command,
                0,
                (
                    '[{"identifier":"qwen2.5-coder-14b-instruct",'
                    '"modelKey":"qwen2.5-coder-14b-instruct","contextLength":16384}]'
                ),
                "",
            )
        return LocalCommandResult(command, 0, "ok", "")

    output = authorized_coder_context_reload_output(
        target_context=8192,
        captain_authorized=True,
        lms_path="lms",
        runner=fake_runner,
    )

    assert "Current live context_window: 16384" in output
    assert "Refused: current live context is already at or above the requested target" in output
    assert not any(call[:2] == ["lms", "load"] for call in calls)


def test_command_doctrine_exists_in_readme_and_registry() -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    registry = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))

    assert DOCTRINE in " ".join(readme.split())
    assert registry["command_doctrine"]["principle"] == DOCTRINE
    assert "The GUI is the primary Captain-facing interface." in registry["command_doctrine"]["workflow_rules"]
