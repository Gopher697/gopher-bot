from __future__ import annotations

from pathlib import Path

import yaml

from starship_command.starship_console import build_codex_prompt, build_specialist_brief, load_registry, route_task


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "starship_command" / "command_registry.yaml"


def test_registry_loads_and_has_explicit_routing_rules() -> None:
    registry = load_registry(REGISTRY_PATH)

    assert registry["version"] == 2
    assert "routing_rules" in registry
    assert "stations" in registry["routing_rules"]
    assert registry["routing_rules"]["stations"]["engineering"]["keyword_weights"]
    assert registry["routing_rules"]["stations"]["modding"]["keyword_weights"]


def test_authority_values_are_limited() -> None:
    registry = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    allowed = {True, False, "scoped"}
    values: list[object] = []

    def collect_authority(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "authority":
                    values.append(value)
                collect_authority(value)
        elif isinstance(node, list):
            for item in node:
                collect_authority(item)

    collect_authority(registry)

    assert values
    assert all(value in allowed for value in values)


def test_route_readme_examples() -> None:
    registry = load_registry(REGISTRY_PATH)
    cases = [
        (
            "debug the nostdrec recruit screen issue in the CoE5 mod",
            "engineering",
            ["modding"],
            True,
        ),
        (
            "turn Er Gen corpus notes into a usable Codex reference system",
            "archives",
            [],
            True,
        ),
        (
            "Resume Cultivation GSG lane boundaries",
            "archives",
            ["first_officer", "design"],
            True,
        ),
        (
            "WorldBox Xianni version/source confusion",
            "archives",
            ["modding", "tactical"],
            True,
        ),
        (
            "reusable game-agent workspace for a new game",
            "first_officer",
            ["science"],
            True,
        ),
    ]

    for task, primary, support, specialist in cases:
        route = route_task(task, registry)
        assert route["primary_station"] == primary
        for station in support:
            assert station in route["supporting_stations"]
        assert route["specialist_recommended"] is specialist


def test_tactical_supports_risky_implementation_instead_of_primary() -> None:
    registry = load_registry(REGISTRY_PATH)

    route = route_task("implement a risky delete script for repo cleanup", registry)

    assert route["primary_station"] == "engineering"
    assert "tactical" in route["supporting_stations"]


def test_codex_prompt_includes_limitations_and_repo_safety() -> None:
    registry = load_registry(REGISTRY_PATH)

    prompt = build_codex_prompt("debug a repo test failure", registry)

    assert "template-based output" in prompt
    assert "[[UNKNOWN: fill in before use]]" in prompt
    assert "Do not commit unless explicitly instructed." in prompt
    assert "Show git status --short after changes." in prompt
    assert "Required Context To Inspect First" in prompt
    assert "Expected Output" in prompt


def test_spawn_specialist_brief_has_required_sections() -> None:
    registry = load_registry(REGISTRY_PATH)

    brief = build_specialist_brief("turn Er Gen corpus notes into a usable Codex reference system", registry)

    assert "No autonomous agent was launched" in brief
    assert "Station: Archivist" in brief
    assert "Mission: turn Er Gen corpus notes into a usable Codex reference system" in brief
    assert "Required Context" in brief
    assert "Authority: scoped" in brief
    assert "Expected Output" in brief
    assert "Retirement Condition" in brief
    assert "Escalation Rules" in brief
