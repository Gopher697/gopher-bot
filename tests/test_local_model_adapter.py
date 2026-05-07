from __future__ import annotations

from pathlib import Path

import pytest

from starship_command.local_model_adapter import (
    LocalModelBridgeError,
    LocalModelConfig,
    build_engineering_dry_run,
    build_engineering_test_payload,
    ensure_model_available,
    format_engineering_result,
    list_models,
    load_local_model_config,
    require_local_http_endpoint,
    run_engineering_test,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "starship_command" / "command_registry.yaml"


def config() -> LocalModelConfig:
    return LocalModelConfig(
        endpoint="http://localhost:1234/v1",
        model="qwen2.5-coder-14b-instruct",
        timeout_seconds=30,
        temperature=0.1,
        max_tokens=600,
        engineering_test_prompt="Suggest one unit test.",
    )


def test_registry_local_model_config_loads_defaults() -> None:
    loaded = load_local_model_config(REGISTRY_PATH)

    assert loaded.endpoint == "http://localhost:1234/v1"
    assert loaded.model == "qwen2.5-coder-14b-instruct"
    assert loaded.engineering_test_prompt.startswith("Inspect this Starship Command routing scenario")


def test_endpoint_must_be_loopback_http() -> None:
    assert require_local_http_endpoint("http://127.0.0.1:1234/v1") == "http://127.0.0.1:1234/v1"

    with pytest.raises(LocalModelBridgeError):
        require_local_http_endpoint("https://localhost:1234/v1")
    with pytest.raises(LocalModelBridgeError):
        require_local_http_endpoint("http://example.com/v1")


def test_list_models_reads_openai_compatible_models_response() -> None:
    calls = []

    def fake_request(method: str, url: str, payload: dict | None, timeout: float) -> dict:
        calls.append((method, url, payload, timeout))
        return {"data": [{"id": "qwen2.5-coder-14b-instruct"}, {"id": "qwen2.5-3b-instruct"}]}

    models = list_models(config(), fake_request)

    assert models == ["qwen2.5-coder-14b-instruct", "qwen2.5-3b-instruct"]
    assert calls == [("GET", "http://localhost:1234/v1/models", None, 30)]


def test_unavailable_model_fails_before_chat_request() -> None:
    calls = []

    def fake_request(method: str, url: str, payload: dict | None, timeout: float) -> dict:
        calls.append((method, url, payload, timeout))
        return {"data": [{"id": "qwen2.5-3b-instruct"}]}

    with pytest.raises(LocalModelBridgeError, match="was not listed"):
        ensure_model_available(config(), fake_request)

    assert len(calls) == 1
    assert calls[0][0] == "GET"


def test_engineering_test_uses_fixed_prompt_and_measures_latency() -> None:
    calls = []
    timer_values = iter([10.0, 12.25])

    def fake_request(method: str, url: str, payload: dict | None, timeout: float) -> dict:
        calls.append((method, url, payload, timeout))
        if method == "GET":
            return {"data": [{"id": "qwen2.5-coder-14b-instruct"}]}
        return {
            "choices": [
                {
                    "message": {
                        "content": "Add a route test that asserts engineering primary and modding support."
                    }
                }
            ]
        }

    result = run_engineering_test(config(), fake_request, timer=lambda: next(timer_values))

    assert result["model"] == "qwen2.5-coder-14b-instruct"
    assert result["endpoint"] == "http://localhost:1234/v1"
    assert result["latency_seconds"] == pytest.approx(2.25)
    assert result["human_usability_judgment"] == "pending"
    assert "engineering primary" in result["response_text"]

    chat_payload = calls[1][2]
    assert calls[0][0] == "GET"
    assert calls[1][0] == "POST"
    assert calls[1][1] == "http://localhost:1234/v1/chat/completions"
    assert chat_payload["model"] == "qwen2.5-coder-14b-instruct"
    assert "Task: Suggest one unit test." in chat_payload["messages"][1]["content"]
    assert "Propose one Starship Command routing unit test." in chat_payload["messages"][1]["content"]
    assert "Do not edit files" in chat_payload["messages"][0]["content"]
    assert "do not invent them" in chat_payload["messages"][0]["content"]
    assert chat_payload["temperature"] == 0.1
    assert chat_payload["top_p"] == 0.8
    assert chat_payload["top_k"] == 40
    assert chat_payload["max_tokens"] == 700
    assert "tools" not in chat_payload


def test_engineering_payload_can_be_rendered_without_network_call() -> None:
    payload = build_engineering_test_payload(config())
    dry_run = build_engineering_dry_run(config())

    assert payload["model"] == "qwen2.5-coder-14b-instruct"
    assert payload["messages"][0]["role"] == "system"
    assert "local Engineering review assistant for Starship Command" in payload["messages"][0]["content"]
    assert "focus on Starship routing behavior, not game simulation" in payload["messages"][0]["content"]
    assert "Do not invent imports or modules unless provided" in payload["messages"][0]["content"]
    assert "Do not edit files" in payload["messages"][0]["content"]
    assert "Task: Suggest one unit test." in payload["messages"][1]["content"]
    assert payload["top_p"] == 0.8
    assert payload["top_k"] == 40
    assert payload["max_tokens"] == 700
    assert dry_run["network_call_made"] is False
    assert dry_run["prompt_profile"] == "engineering_test_design"
    assert dry_run["url"] == "http://localhost:1234/v1/chat/completions"
    assert dry_run["payload"] == payload


def test_format_engineering_result_includes_human_judgment_marker() -> None:
    output = format_engineering_result(
        {
            "endpoint": "http://localhost:1234/v1",
            "model": "qwen2.5-coder-14b-instruct",
            "latency_seconds": 1.23456,
            "human_usability_judgment": "pending",
            "usability_note": "Human review required; the adapter does not auto-grade model quality.",
            "response_text": "A focused route test.",
        }
    )

    assert "Latency: 1.235s" in output
    assert "Human usability judgment: pending" in output
    assert "A focused route test." in output
