from __future__ import annotations

from pathlib import Path

import yaml

from starship_command.starship_core import (
    add_codex_order,
    create_initial_state,
    deploy_specialist,
    load_registry,
    route_task,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "starship_command" / "command_registry.yaml"


def registry() -> dict:
    return load_registry(REGISTRY_PATH)


def test_registry_authority_values_are_constrained() -> None:
    data = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    values = []

    def collect(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "authority":
                    values.append(value)
                collect(value)
        elif isinstance(node, list):
            for item in node:
                collect(item)

    collect(data)

    assert values
    assert set(values) <= {True, False, "scoped"}


def test_nostdrec_debug_routes_engineering_with_modding_support_only() -> None:
    route = route_task("debug the nostdrec recruit screen issue in the CoE5 mod", registry())

    assert route["primary_station"] == "engineering"
    assert "modding" in route["supporting_stations"]
    assert "tactical" not in route["supporting_stations"]
    assert route["specialist_recommended"] is True


def test_worldbox_source_confusion_routes_archives_with_modding_and_tactical_support() -> None:
    route = route_task("WorldBox Xianni version/source confusion", registry())

    assert route["primary_station"] == "archives"
    assert "modding" in route["supporting_stations"]
    assert "tactical" in route["supporting_stations"]


def test_cultivation_lane_boundary_continuity_routes_archives() -> None:
    route = route_task("Resume Cultivation GSG lane boundaries", registry())

    assert route["primary_station"] == "archives"
    assert "design" in route["supporting_stations"]


def test_cultivation_design_lane_work_routes_design() -> None:
    route = route_task("design a Cultivation GSG faction roadmap and system design lane", registry())

    assert route["primary_station"] == "design"


def test_game_agent_workspace_planning_routes_command_with_science_support() -> None:
    route = route_task("reusable game-agent workspace for a new game", registry())

    assert route["primary_station"] == "first_officer"
    assert "science" in route["supporting_stations"]


def test_save_state_gameplay_work_routes_science() -> None:
    route = route_task("build save state decision support for a Dwarf Fortress playthrough", registry())

    assert route["primary_station"] == "science"
    assert "engineering" in route["supporting_stations"]


def test_tactical_primary_only_for_explicit_risk_review() -> None:
    risky_impl = route_task("implement a risky delete script for repo cleanup", registry())
    explicit_review = route_task("risk review for live DLL overwrite in WorldBox Xianni", registry())

    assert risky_impl["primary_station"] == "engineering"
    assert "tactical" in risky_impl["supporting_stations"]
    assert explicit_review["primary_station"] == "tactical"


def test_specialist_deployment_creates_tracked_record_not_agent() -> None:
    reg = registry()
    state = create_initial_state(reg)

    result = deploy_specialist(state, "turn Er Gen corpus notes into a usable Codex reference system", reg)

    assert result["specialist"]["station"] == "archives"
    assert result["specialist"]["status"] == "assigned"
    assert "No autonomous agent was launched" in result["specialist"]["note"]
    assert state["divisions"]["archives"]["specialists"]


def test_codex_order_state_includes_template_limitations() -> None:
    reg = registry()
    state = create_initial_state(reg)

    result = add_codex_order(state, "debug a repo test failure", reg)

    assert "template-based output" in result["output"]
    assert "[[UNKNOWN: fill in before use]]" in result["output"]
    assert "Do not commit unless explicitly instructed." in result["output"]
    assert "Show git status --short after changes." in result["output"]
