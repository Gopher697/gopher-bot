from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


WORKBENCH_ROOT = Path(__file__).resolve().parents[1]
SELF_PATH = Path(__file__).resolve()
GAME_AGENT_CORE_ROOT = Path("D:/GameAgentCore")

SUPPORTED_MISSION_TYPE = "survey_dossier"
SUPPORTED_MODE = "read_only"


def _target_configs() -> dict[str, dict[str, Any]]:
    return {
        "gopher-workbench-mcp": {
            "target": "gopher-workbench-mcp",
            "classification": "Workbench MCP server and registered project authority layer.",
            "summary": (
                "The Workbench project is a conservative local MCP server with repo-local orientation, "
                "registered project boundaries, and read-only defaults for normal inspection."
            ),
            "authority_files": [
                WORKBENCH_ROOT / "WORKBENCH_INDEX.md",
                WORKBENCH_ROOT / "PROJECT_REGISTRY.md",
                WORKBENCH_ROOT / "README.md",
                WORKBENCH_ROOT / "PROJECT.md",
            ],
            "known_risks": [
                "The registry flags whether README Current Local Setup is canonical or a dated snapshot as an open question.",
                "Session notes, staging folders, raw imports, and old handoffs remain historical unless promoted.",
            ],
            "recommended_next_action": (
                "Keep using WORKBENCH_INDEX.md and PROJECT_REGISTRY.md before project-specific work."
            ),
        },
        "starship_command": {
            "target": "starship_command",
            "classification": "U.S.S. Wayfarer ship-local command package inside gopher-workbench-mcp.",
            "summary": (
                "Starship Command is the drydock command package for U.S.S. Wayfarer. "
                "Its current role is bounded mission routing and artifact generation, not an autonomous runtime."
            ),
            "authority_files": [
                WORKBENCH_ROOT / "starship_command" / "README.md",
                WORKBENCH_ROOT / "starship_command" / "command_registry.yaml",
                WORKBENCH_ROOT / "starship_command" / "starship_core.py",
            ],
            "known_risks": [
                "Mission dossiers are temporary assignments and must not become the ship identity.",
                "Local model and GUI operations remain drydock workflows with explicit authorization boundaries.",
            ],
            "recommended_next_action": (
                "Use this survey dossier loop as the first proof that Wayfarer can complete one real mission."
            ),
        },
        "game-agent-core": {
            "target": "game-agent-core",
            "classification": "External game-agent architecture and doctrine project; not the ship.",
            "summary": (
                "GameAgentCore defines shared game-agent doctrine, safety boundaries, and operating loops. "
                "It is a survey target only here, separate from U.S.S. Wayfarer."
            ),
            "authority_files": [
                GAME_AGENT_CORE_ROOT / "AGENTS.md",
                GAME_AGENT_CORE_ROOT / "GAME_AGENT_LOOP.md",
                GAME_AGENT_CORE_ROOT / "AUTONOMY_LEVELS.md",
                GAME_AGENT_CORE_ROOT / "SAFETY_RULES_GLOBAL.md",
            ],
            "known_risks": [
                "Game-specific memory belongs in each game's own workspace, not in GameAgentCore.",
                "Save, online, purchase, and irreversible-action boundaries require explicit human approval.",
            ],
            "recommended_next_action": (
                "Treat GameAgentCore as a read-only doctrine survey target until a later mission scopes a test use."
            ),
        },
    }


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(WORKBENCH_ROOT))
    except ValueError:
        return str(resolved)


def _first_heading(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                return stripped.lstrip("#").strip()
    except OSError:
        return ""
    return ""


def _evidence_for_files(paths: list[Path]) -> list[str]:
    evidence: list[str] = []
    for path in paths:
        display = _display_path(path)
        if path.exists():
            heading = _first_heading(path)
            if heading:
                evidence.append(f"{display}: declares {heading}.")
            else:
                evidence.append(f"{display}: present as a known authority file.")
        else:
            evidence.append(f"{display}: expected authority file is missing.")
    return evidence


def _artifact(
    *,
    mission_type: str,
    target: str,
    summary: str,
    classification: str,
    authority_files: list[Path],
    known_risks: list[str],
    recommended_next_action: str,
    evidence: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "type": mission_type,
        "target": target,
        "summary": summary,
        "classification": classification,
        "authority_files": [_display_path(path) for path in authority_files],
        "known_risks": known_risks,
        "recommended_next_action": recommended_next_action,
        "evidence": evidence if evidence is not None else _evidence_for_files(authority_files),
    }


def _known_existing_paths(target: str) -> list[Path]:
    paths = [WORKBENCH_ROOT / "PROJECT_REGISTRY.md", SELF_PATH]
    config = _target_configs().get(target)
    if config:
        paths.extend(config["authority_files"])
    return [path for path in paths if path.exists()]


def _evidence_references_existing_path(target: str, evidence: list[Any]) -> bool:
    evidence_text = "\n".join(str(item) for item in evidence)
    for path in _known_existing_paths(target):
        display = _display_path(path)
        resolved = str(path.resolve())
        if display in evidence_text or resolved in evidence_text or path.name in evidence_text:
            return True
    return False


def _flatten_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_flatten_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_flatten_text(item) for item in value)
    return str(value)


def _read_only_claim_issues(report: dict[str, Any]) -> list[str]:
    text = _flatten_text({key: value for key, value in report.items() if key != "validation"}).casefold()
    disallowed_claims = [
        "file write",
        "file writes",
        "wrote ",
        "written ",
        "saved output file",
        "created output file",
        "modified file",
        "edited file",
        "command execution",
        "executed command",
        "ran command",
        "shell command executed",
        "called mcp",
        "used mcp tool",
        "game input",
        "sent game input",
        "clicked ",
        "typed ",
        "pressed key",
        "deletion",
        "deleted ",
        "removed file",
        "network action",
        "network request",
        "network call",
        "external api call",
        "http://",
        "https://",
    ]
    return [f"read_only report claims prohibited action: {claim.strip()}" for claim in disallowed_claims if claim in text]


def validate_report(report: dict[str, Any], request: dict[str, Any] | None = None) -> dict[str, Any]:
    issues: list[str] = []
    target = str(report.get("target") or "")
    artifact = report.get("artifact")

    if report.get("status") not in {"succeeded", "failed", "blocked"}:
        issues.append("report status must be one of succeeded, failed, or blocked")
    if report.get("mission_type") != SUPPORTED_MISSION_TYPE:
        issues.append("mission_type must be survey_dossier")
    if not target:
        issues.append("target must be present")
    if not isinstance(artifact, dict):
        issues.append("artifact must be present")
        artifact = {}
    if artifact.get("type") != report.get("mission_type"):
        issues.append("artifact type must match mission_type")
    if artifact.get("target") != target:
        issues.append("artifact target must match report target")
    if not str(artifact.get("summary") or "").strip():
        issues.append("artifact summary must be non-empty")
    if not str(artifact.get("classification") or "").strip():
        issues.append("artifact classification must be non-empty")

    evidence = artifact.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        issues.append("artifact evidence must be a non-empty list")
        evidence = []
    elif not _evidence_references_existing_path(target, evidence):
        issues.append("artifact evidence must reference at least one real known file/path")

    if request is not None:
        if request.get("mission_type") != SUPPORTED_MISSION_TYPE:
            issues.append(f"unsupported mission_type: {request.get('mission_type')!r}")
        if request.get("mode") != SUPPORTED_MODE:
            issues.append(f"unsupported mode: {request.get('mode')!r}; only read_only is supported")
        if request.get("target_project") not in _target_configs():
            issues.append(f"unknown target_project: {request.get('target_project')!r}")

    issues.extend(_read_only_claim_issues(report))
    return {"passed": not issues, "issues": issues}


def _finish_report(
    *,
    status: str,
    mission_type: str,
    target: str,
    artifact: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    report = {
        "status": status,
        "mission_type": mission_type,
        "target": target,
        "artifact": artifact,
        "validation": {"passed": False, "issues": []},
    }
    report["validation"] = validate_report(report, request)
    if status == "succeeded" and not report["validation"]["passed"]:
        report["status"] = "failed"
    return report


def run_mission(request: dict) -> dict:
    if not isinstance(request, dict):
        request = {}

    mission_type = str(request.get("mission_type") or "")
    target = str(request.get("target_project") or "")
    mode = str(request.get("mode") or "")

    if mission_type != SUPPORTED_MISSION_TYPE:
        artifact = _artifact(
            mission_type=mission_type,
            target=target,
            summary=f"Unsupported mission_type {mission_type!r}; v0 only supports survey_dossier.",
            classification="unsupported_mission_type",
            authority_files=[SELF_PATH],
            known_risks=["No survey dossier was produced because the mission type is outside v0 scope."],
            recommended_next_action="Retry with mission_type set to survey_dossier.",
            evidence=[f"{_display_path(SELF_PATH)}: v0 mission type guard refused the request."],
        )
        return _finish_report(
            status="failed",
            mission_type=mission_type,
            target=target,
            artifact=artifact,
            request=request,
        )

    if mode != SUPPORTED_MODE:
        artifact = _artifact(
            mission_type=mission_type,
            target=target,
            summary="Blocked: v0 mission runner only accepts read_only mode.",
            classification="blocked_read_only_boundary",
            authority_files=[SELF_PATH],
            known_risks=["The requested mode is outside the first mission loop boundary."],
            recommended_next_action="Retry with mode set to read_only.",
            evidence=[f"{_display_path(SELF_PATH)}: read-only guard refused the request."],
        )
        return _finish_report(
            status="blocked",
            mission_type=mission_type,
            target=target,
            artifact=artifact,
            request=request,
        )

    config = _target_configs().get(target)
    if config is None:
        artifact = _artifact(
            mission_type=mission_type,
            target=target,
            summary=f"Unknown target_project {target!r}; no v0 survey target is configured.",
            classification="unsupported_target",
            authority_files=[WORKBENCH_ROOT / "PROJECT_REGISTRY.md"],
            known_risks=["Unknown targets are refused until they are deliberately added to the v0 mission target map."],
            recommended_next_action=(
                "Use one of: gopher-workbench-mcp, starship_command, or game-agent-core."
            ),
            evidence=[
                f"{_display_path(WORKBENCH_ROOT / 'PROJECT_REGISTRY.md')}: registered project names define the target boundary."
            ],
        )
        return _finish_report(
            status="failed",
            mission_type=mission_type,
            target=target,
            artifact=artifact,
            request=request,
        )

    artifact = _artifact(
        mission_type=mission_type,
        target=config["target"],
        summary=config["summary"],
        classification=config["classification"],
        authority_files=config["authority_files"],
        known_risks=config["known_risks"],
        recommended_next_action=config["recommended_next_action"],
    )
    return _finish_report(
        status="succeeded",
        mission_type=mission_type,
        target=config["target"],
        artifact=artifact,
        request=request,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one read-only U.S.S. Wayfarer v0 mission.")
    parser.add_argument("target_project", help="Target project to survey.")
    parser.add_argument("--mission-type", default=SUPPORTED_MISSION_TYPE)
    parser.add_argument("--mode", default=SUPPORTED_MODE)
    args = parser.parse_args(argv)

    report = run_mission(
        {
            "mission_type": args.mission_type,
            "target_project": args.target_project,
            "mode": args.mode,
        }
    )
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
