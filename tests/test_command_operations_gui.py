from __future__ import annotations

from starship_command import command_operations_gui
from starship_command.local_model_adapter import LocalModelBridgeError


def test_local_model_readiness_output_uses_doctor_helpers(monkeypatch) -> None:
    calls = []

    def fake_load_config() -> str:
        calls.append("load")
        return "config"

    def fake_build_report(config: str) -> dict:
        calls.append(f"build:{config}")
        return {"endpoint_reachable": True}

    def fake_format_report(report: dict) -> str:
        calls.append(f"format:{report['endpoint_reachable']}")
        return "formatted readiness report"

    monkeypatch.setattr(command_operations_gui, "load_doctor_config", fake_load_config)
    monkeypatch.setattr(command_operations_gui, "build_readiness_report", fake_build_report)
    monkeypatch.setattr(command_operations_gui, "format_readiness_report", fake_format_report)

    output = command_operations_gui.build_local_model_readiness_output()

    assert output == "formatted readiness report"
    assert calls == ["load", "build:config", "format:True"]


def test_local_model_readiness_output_reports_unreachable_guidance(monkeypatch) -> None:
    def fake_load_config() -> str:
        raise LocalModelBridgeError("Could not reach local model endpoint")

    monkeypatch.setattr(command_operations_gui, "load_doctor_config", fake_load_config)

    output = command_operations_gui.build_local_model_readiness_output()

    assert "Endpoint reachable: no" in output
    assert "Could not reach local model endpoint" in output
    assert "LM Studio is not running." in output
    assert "LM Studio local server is disabled." in output
    assert "The configured endpoint or port differs" in output
    assert "The expected model is not loaded" in output
