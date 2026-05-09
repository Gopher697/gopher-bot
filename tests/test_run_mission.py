from __future__ import annotations

import json

from starship_command.__main__ import main as starship_main
from starship_command.run_mission import run_mission
from tests.helpers import make_workspace


def survey(target: str) -> dict:
    return run_mission(
        {
            "mission_type": "survey_dossier",
            "target_project": target,
            "mode": "read_only",
        }
    )


def assert_successful_survey(report: dict, target: str) -> None:
    assert report["status"] == "succeeded"
    assert report["mission_type"] == "survey_dossier"
    assert report["target"] == target
    assert report["validation"] == {"passed": True, "issues": []}
    assert report["artifact"]["type"] == "survey_dossier"
    assert report["artifact"]["target"] == target
    assert report["artifact"]["summary"]
    assert report["artifact"]["classification"]
    assert report["artifact"]["evidence"]


def test_successful_survey_for_gopher_workbench_mcp() -> None:
    report = survey("gopher-workbench-mcp")

    assert_successful_survey(report, "gopher-workbench-mcp")
    assert "WORKBENCH_INDEX.md" in "\n".join(report["artifact"]["authority_files"])


def test_successful_survey_for_starship_command() -> None:
    report = survey("starship_command")

    assert_successful_survey(report, "starship_command")
    assert "U.S.S. Wayfarer" in report["artifact"]["classification"]
    assert "GameAgentCore" not in report["artifact"]["classification"]


def test_successful_survey_for_game_agent_core() -> None:
    report = survey("game-agent-core")

    assert_successful_survey(report, "game-agent-core")
    assert "not the ship" in report["artifact"]["classification"]
    assert "GameAgentCore" in report["artifact"]["summary"]


def test_invalid_mission_type_fails_cleanly() -> None:
    report = run_mission(
        {
            "mission_type": "inventory",
            "target_project": "gopher-workbench-mcp",
            "mode": "read_only",
        }
    )

    assert report["status"] == "failed"
    assert report["validation"]["passed"] is False
    assert any("unsupported mission_type" in issue for issue in report["validation"]["issues"])


def test_non_read_only_mode_blocks_cleanly() -> None:
    report = run_mission(
        {
            "mission_type": "survey_dossier",
            "target_project": "gopher-workbench-mcp",
            "mode": "write",
        }
    )

    assert report["status"] in {"blocked", "failed"}
    assert report["validation"]["passed"] is False
    assert any("unsupported mode" in issue for issue in report["validation"]["issues"])


def test_unknown_target_fails_cleanly() -> None:
    report = survey("unknown-project")

    assert report["status"] == "failed"
    assert report["validation"]["passed"] is False
    assert any("unknown target_project" in issue for issue in report["validation"]["issues"])


def test_package_cli_run_mission_prints_json(capsys) -> None:
    exit_code = starship_main(
        [
            "run-mission",
            "--target",
            "gopher-workbench-mcp",
            "--type",
            "survey_dossier",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["status"] == "succeeded"
    assert payload["mission_type"] == "survey_dossier"
    assert payload["target"] == "gopher-workbench-mcp"
    assert payload["validation"] == {"passed": True, "issues": []}


def test_package_cli_run_mission_writes_utf8_json_output(capsys) -> None:
    output = make_workspace("cli-output") / "nested" / "mission.json"

    exit_code = starship_main(
        [
            "run-mission",
            "--target",
            "game-agent-core",
            "--type",
            "survey_dossier",
            "--output",
            str(output),
        ]
    )

    captured = capsys.readouterr()
    raw = output.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    assert exit_code == 0
    assert captured.out == ""
    assert raw[:2] != b"\xff\xfe"
    assert payload["status"] == "succeeded"
    assert payload["target"] == "game-agent-core"
    assert payload["validation"] == {"passed": True, "issues": []}


def test_package_cli_output_preserves_nonzero_exit_for_failed_report() -> None:
    output = make_workspace("cli-output-failed") / "failed" / "mission.json"

    exit_code = starship_main(
        [
            "run-mission",
            "--target",
            "unknown-project",
            "--type",
            "survey_dossier",
            "--output",
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert payload["status"] == "failed"
    assert payload["validation"]["passed"] is False
