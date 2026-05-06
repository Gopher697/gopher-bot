from __future__ import annotations

from pathlib import Path

import pytest

from starship_command.local_model_adapter import LocalModelBridgeError
from starship_command.local_model_server_doctor import (
    DoctorConfig,
    ObservedModel,
    ReadinessTest,
    build_readiness_dry_run,
    build_readiness_payload,
    build_readiness_report,
    check_endpoint,
    format_check,
    format_model_list,
    format_readiness_report,
    list_model_infos,
    load_doctor_config,
    validate_doctor_endpoint,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "starship_command" / "command_registry.yaml"


def doctor_config() -> DoctorConfig:
    registry_models = [
        ObservedModel("qwen/qwen3.5-9b", "qwen_qwen3_5_9b", "fast triage candidate", 8192),
        ObservedModel(
            "qwen2.5-coder-14b-instruct",
            "qwen2_5_coder_14b_instruct",
            "deep Engineering consult candidate",
            2048,
        ),
        ObservedModel("qwen2.5-3b-instruct", "qwen2_5_3b_instruct", "fast triage candidate"),
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
        registry_models=registry_models,
        observed_models=registry_models[:2],
        readiness_tests=[
            ReadinessTest(
                model_id="qwen/qwen3.5-9b",
                prompt_name="first_officer_triage",
                prompt="Triage a vague workflow mission.",
                system_prompt="You are a First Officer triage assistant.",
                role_classification="fast triage candidate",
                max_tokens=120,
            ),
            ReadinessTest(
                model_id="qwen2.5-coder-14b-instruct",
                prompt_name="engineering_unit_test",
                prompt="Suggest one routing unit test.",
                system_prompt="You are an Engineering review assistant.",
                role_classification="deep Engineering consult candidate",
                max_tokens=160,
            ),
            ReadinessTest(
                model_id="qwen2.5-3b-instruct",
                prompt_name="lightweight_engineering_triage",
                prompt="Summarize the route assertions.",
                system_prompt="You are a lightweight Engineering triage assistant.",
                role_classification="fast triage candidate",
                max_tokens=120,
            ),
        ],
        allowed_divisions=[
            "Command Division",
            "Engineering Division",
            "Computer Core / Archives",
            "Tactical / Safety",
            "Science / Game Intelligence",
            "Modding Division",
            "Design Bureau",
        ],
    )


def test_registry_doctor_config_loads() -> None:
    config = load_doctor_config(REGISTRY_PATH)

    assert config.endpoint == "http://localhost:1234/v1"
    assert config.allow_non_local_endpoint is False
    assert config.low_context_window_threshold == 2048
    assert any(test.model_id == "qwen2.5-coder-14b-instruct" for test in config.readiness_tests)
    assert any(test.prompt_profile == "first_officer_triage" for test in config.readiness_tests)
    assert any(test.prompt_profile == "engineering_test_design" for test in config.readiness_tests)


def test_endpoint_refuses_non_local_without_explicit_flag() -> None:
    assert validate_doctor_endpoint("http://localhost:1234/v1") == "http://localhost:1234/v1"

    with pytest.raises(LocalModelBridgeError):
        validate_doctor_endpoint("https://localhost:1234/v1")
    with pytest.raises(LocalModelBridgeError):
        validate_doctor_endpoint("http://example.com/v1")

    assert validate_doctor_endpoint("http://example.com/v1", allow_non_local_endpoint=True) == "http://example.com/v1"


def test_mocked_model_listing_reports_context_when_available() -> None:
    def fake_request(method: str, url: str, payload: dict | None, timeout: float) -> dict:
        assert method == "GET"
        assert url == "http://localhost:1234/v1/models"
        return {
            "data": [
                {"id": "qwen/qwen3.5-9b", "context_length": 8192},
                {"id": "qwen2.5-coder-14b-instruct", "metadata": {"n_ctx": 2048}},
            ]
        }

    models = list_model_infos(doctor_config(), fake_request)
    output = format_model_list(doctor_config(), models)

    assert models[0].context_window == 8192
    assert models[1].context_window == 2048
    assert "qwen/qwen3.5-9b | context_window: 8192" in output
    assert "qwen2.5-coder-14b-instruct | context_window: 2048" in output
    assert "Registry/user-observed models visible:" in output


def test_context_window_unknown_when_endpoint_does_not_expose_it() -> None:
    def fake_request(method: str, url: str, payload: dict | None, timeout: float) -> dict:
        return {"data": [{"id": "qwen/qwen3.5-9b"}]}

    models = list_model_infos(doctor_config(), fake_request)
    output = format_model_list(doctor_config(), models)

    assert models[0].context_window is None
    assert "qwen/qwen3.5-9b | context_window: unknown" in output


def test_endpoint_timeout_is_reported_safely() -> None:
    def fake_request(method: str, url: str, payload: dict | None, timeout: float) -> dict:
        raise LocalModelBridgeError("Could not reach local model endpoint")

    result = check_endpoint(doctor_config(), fake_request)
    output = format_check(result)
    report_output = format_readiness_report(
        {
            "endpoint": "http://localhost:1234/v1",
            "endpoint_reachable": False,
            "models_visible": [],
            "registry_models_visible": [],
            "user_observed_models_missing": [],
            "models_tested": [],
            "failures": [result["error"]],
            "human_judgment_required": True,
        }
    )

    assert result["reachable"] is False
    assert "Reachable: no" in output
    assert "Could not reach local model endpoint" in output
    assert "LM Studio is not running." in report_output
    assert "LM Studio local server is disabled." in report_output
    assert "endpoint or port differs" in report_output
    assert "model is not loaded" in report_output


def test_readiness_report_runs_available_tests_and_skips_missing_models() -> None:
    calls = []
    timer_values = iter([1.0, 3.5, 10.0, 30.199])

    def fake_request(method: str, url: str, payload: dict | None, timeout: float) -> dict:
        calls.append((method, url, payload, timeout))
        if method == "GET":
            return {
                "data": [
                    {"id": "qwen/qwen3.5-9b", "context_length": 8192},
                    {"id": "qwen2.5-coder-14b-instruct", "context_length": 2048},
                ]
            }
        if payload["model"] == "qwen/qwen3.5-9b":
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                "Primary division: Engineering Division\n"
                                "Supporting divisions: Modding Division\n"
                                "Risk flags: None\n"
                                "Specialist recommended: yes\n"
                                "One-sentence reason: A repo debugging mission with mod context."
                            )
                        }
                    }
                ]
            }
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            "Test intent: Verify routing.\n"
                            "Assertions: Engineering Division remains primary.\n"
                            "Notes: No imports or modules were invented."
                        )
                    }
                }
            ]
        }

    report = build_readiness_report(doctor_config(), fake_request, timer=lambda: next(timer_values))
    output = format_readiness_report(report)

    assert report["endpoint_reachable"] is True
    assert report["registry_models_visible"] == ["qwen/qwen3.5-9b", "qwen2.5-coder-14b-instruct"]
    assert report["user_observed_models_missing"] == []
    assert [result["model_id"] for result in report["models_tested"]] == [
        "qwen/qwen3.5-9b",
        "qwen2.5-coder-14b-instruct",
    ]
    assert "latency: 20.199s" in output
    assert "Schema: pass" in output
    assert "Division names: yes" in output
    assert "Trust gate: human_review_required" in output
    assert "qwen2.5-3b-instruct" not in [call[2]["model"] for call in calls if call[0] == "POST"]
    assert all("tools" not in call[2] for call in calls if call[0] == "POST")


def test_readiness_report_includes_validation_failure_fields() -> None:
    timer_values = iter([1.0, 2.0])

    def fake_request(method: str, url: str, payload: dict | None, timeout: float) -> dict:
        if method == "GET":
            return {"data": [{"id": "qwen/qwen3.5-9b", "context_length": 8192}]}
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            "Primary division: Software Engineering\n"
                            "Supporting divisions: Quality Assurance\n"
                            "Risk flags: None\n"
                            "Specialist recommended: yes\n"
                            "One-sentence reason: A generic QA path."
                        )
                    }
                }
            ]
        }

    report = build_readiness_report(doctor_config(), fake_request, timer=lambda: next(timer_values))
    result = report["models_tested"][0]
    output = format_readiness_report(report)

    assert result["schema_valid"] is True
    assert result["division_vocabulary_valid"] == "no"
    assert "invalid_division" in result["warnings"]
    assert result["trust_gate"] == "fail"
    assert "Schema: pass" in output
    assert "Division names: no" in output
    assert "Warnings: invalid_division" in output
    assert "invalid_divisions: Software Engineering, Quality Assurance" in output


def test_readiness_payloads_can_be_rendered_without_network_call() -> None:
    config = doctor_config()
    payload = build_readiness_payload(config, config.readiness_tests[0])
    dry_run = build_readiness_dry_run(config)

    assert payload["model"] == "qwen/qwen3.5-9b"
    assert payload["messages"][0]["role"] == "system"
    assert "First Officer triage assistant" in payload["messages"][0]["content"]
    assert "Do not edit files" in payload["messages"][0]["content"]
    assert payload["messages"][1] == {"role": "user", "content": "Triage a vague workflow mission."}
    assert dry_run["network_call_made"] is False
    assert dry_run["url"] == "http://localhost:1234/v1/chat/completions"
    assert [item["prompt_name"] for item in dry_run["tests"]] == [
        "first_officer_triage",
        "engineering_unit_test",
        "lightweight_engineering_triage",
    ]
    assert dry_run["tests"][0]["payload"] == payload


def test_registry_readiness_payloads_include_crew_prompt_profiles() -> None:
    config = load_doctor_config(REGISTRY_PATH)
    dry_run = build_readiness_dry_run(config)

    first_officer = next(item for item in dry_run["tests"] if item["model_id"] == "qwen/qwen3.5-9b")
    coder = next(item for item in dry_run["tests"] if item["model_id"] == "qwen2.5-coder-14b-instruct")
    three_b = next(item for item in dry_run["tests"] if item["model_id"] == "qwen2.5-3b-instruct")

    assert first_officer["prompt_profile"] == "first_officer_triage"
    assert "Route means assign a mission to Starship Command divisions or stations" in first_officer["payload"]["messages"][0]["content"]
    assert "Route does not mean gameplay movement, map navigation, UI navigation, or pathfinding" in first_officer["payload"]["messages"][0]["content"]
    assert "debug the nostdrec recruit screen issue" in first_officer["payload"]["messages"][1]["content"]

    assert three_b["prompt_profile"] == "first_officer_triage"
    assert "Failure condition" in three_b["payload"]["messages"][0]["content"]

    assert coder["prompt_profile"] == "engineering_test_design"
    assert "focus on Starship routing behavior, not game simulation" in coder["payload"]["messages"][0]["content"]
    assert "Do not invent imports or modules unless provided" in coder["payload"]["messages"][0]["content"]


def test_low_context_window_is_flagged_as_quality_limitation() -> None:
    def fake_request(method: str, url: str, payload: dict | None, timeout: float) -> dict:
        if method == "GET":
            return {"data": [{"id": "qwen2.5-coder-14b-instruct", "context_window": 2048}]}
        return {"choices": [{"message": {"content": "A route test suggestion."}}]}

    report = build_readiness_report(doctor_config(), fake_request, timer=iter([1.0, 2.0]).__next__)
    output = format_readiness_report(report)

    assert "low programmatic context window (2048)" in output
    assert "likely quality limitation for code/project reasoning" in output


def test_readiness_report_marks_context_unknown_and_requests_lm_studio_verification() -> None:
    def fake_request(method: str, url: str, payload: dict | None, timeout: float) -> dict:
        if method == "GET":
            return {"data": [{"id": "qwen2.5-coder-14b-instruct"}]}
        return {"choices": [{"message": {"content": "A route test suggestion."}}]}

    report = build_readiness_report(doctor_config(), fake_request, timer=iter([1.0, 2.0]).__next__)
    output = format_readiness_report(report)

    assert "context_window: unknown" in output
    assert "verify in LM Studio" in output
    assert "do not compare models directly" in output
