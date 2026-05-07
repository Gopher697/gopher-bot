from __future__ import annotations

from pathlib import Path

from starship_command.model_profiles import (
    apply_profile_to_payload,
    build_profile_compliance,
    context_target_for_model,
    get_model_profile,
    inference_settings_from_payload,
    load_model_profiles,
    model_observation,
    setting_control_summary,
)


ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / "starship_command" / "model_profiles.yaml"


def test_model_profiles_load_required_roles() -> None:
    profiles = load_model_profiles(PROFILE_PATH)

    assert {"first_officer_triage", "engineering_test_design", "visual_inspection", "model_evaluation"} <= set(profiles)
    assert "qwen/qwen3.5-9b" in profiles["first_officer_triage"].intended_models
    assert "qwen2.5-coder-14b-instruct" in profiles["engineering_test_design"].intended_models


def test_setting_control_classifies_load_and_inference_settings() -> None:
    controls = setting_control_summary(PROFILE_PATH)

    assert controls["context_length"] == "load_time_controlled"
    assert controls["temperature"] == "inference_payload_controlled"
    assert controls["top_p"] == "inference_payload_controlled"
    assert controls["thinking_mode"] == "manual_only"
    assert controls["gpu_offload"] == "unknown"


def test_profile_inference_settings_are_applied_to_payload() -> None:
    profile = get_model_profile("first_officer_triage", PROFILE_PATH)
    payload = apply_profile_to_payload({"model": "qwen/qwen3.5-9b", "messages": []}, profile)

    assert inference_settings_from_payload(payload) == {
        "temperature": 0.1,
        "top_p": 0.8,
        "top_k": 40,
        "max_tokens": 500,
    }


def test_profile_compliance_fails_when_context_is_below_target() -> None:
    compliance = build_profile_compliance(
        profile_id="first_officer_triage",
        model_id="qwen/qwen3.5-9b",
        live_context=4096,
        path=PROFILE_PATH,
    )

    assert compliance["context_target"] == 8192
    assert compliance["context_compliance"] == "fail"
    assert "context_below_profile_target" in compliance["warnings"]
    assert compliance["overall_compliance"] == "fail"


def test_profile_compliance_warns_when_gpu_offload_is_zero() -> None:
    compliance = build_profile_compliance(
        profile_id="first_officer_triage",
        model_id="google/gemma-4-26b-a4b",
        live_model={"contextLength": 8192, "gpuOffload": 0},
        path=PROFILE_PATH,
    )

    assert compliance["live_gpu_offload"] == 0
    assert compliance["gpu_offload_compliance"] == "fail"
    assert "gpu_offload_zero" in compliance["warnings"]
    assert compliance["overall_compliance"] == "fail"


def test_profile_compliance_warns_when_thinking_mode_is_enabled_for_schema_test() -> None:
    compliance = build_profile_compliance(
        profile_id="first_officer_triage",
        model_id="google/gemma-4-26b-a4b",
        live_model={"contextLength": 8192, "enableThinking": True},
        path=PROFILE_PATH,
    )

    assert compliance["thinking_mode_target"] is False
    assert compliance["live_thinking_mode"] is True
    assert compliance["thinking_mode_compliance"] == "fail"
    assert "thinking_mode_enabled_for_schema_test" in compliance["warnings"]


def test_gemma_prior_result_is_settings_suspect_not_quality_rejected() -> None:
    compliance = build_profile_compliance(
        profile_id="first_officer_triage",
        model_id="google/gemma-4-26b-a4b",
        live_context=8192,
        path=PROFILE_PATH,
    )

    assert compliance["retest_required"] is True
    assert "settings_suspect_retest_required" in compliance["profile_notes"]
    assert compliance["observed_settings"]["gpu_offload"] == 0
    assert compliance["observed_settings"]["thinking_mode"] is True

    observation = model_observation("google/gemma-4-26b-a4b", PROFILE_PATH)
    assert observation["starship_api_result"]["output_quality"] == "empty/no extractable content"
    assert observation["manual_open_webui_observation"]["approximate_latency_minutes"] == 9
    assert observation["manual_open_webui_observation"]["follow_up_prompt"] == "Xu Qing"
    assert "Klein Moretti" in observation["manual_open_webui_observation"]["follow_up_confabulations"][1]
    assert "unstable factual recall" in observation["manual_open_webui_observation"]["follow_up_quality"]
    assert observation["revised_classification"]["first_officer"] == "not suitable"
    assert observation["revised_classification"]["archives_factual_recall"] == "not suitable"
    assert "response-extraction investigation" in observation["revised_classification"]["future_candidate"]


def test_coder_profile_has_higher_context_override() -> None:
    profile = get_model_profile("engineering_test_design", PROFILE_PATH)

    assert context_target_for_model(profile, "qwen2.5-coder-14b-instruct") == 16384
    assert context_target_for_model(profile, "mistralai/devstral-small-2-2512") == 8192
