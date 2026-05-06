from __future__ import annotations

from starship_command.crew_prompt_pack import load_prompt_pack, render_prompt_profile


def test_crew_prompt_pack_loads_required_profiles() -> None:
    profiles = load_prompt_pack()

    assert set(profiles) >= {
        "first_officer_triage",
        "engineering_test_design",
        "archives_continuity",
        "model_evaluation",
    }


def test_first_officer_prompt_defines_route_as_starship_assignment() -> None:
    rendered = render_prompt_profile(
        "first_officer_triage",
        {"mission": "debug the nostdrec recruit screen issue in the CoE5 mod"},
    )

    assert "Route means assign a mission to Starship Command divisions or stations" in rendered.system_prompt
    assert "Route does not mean gameplay movement, map navigation, UI navigation, or pathfinding" in rendered.system_prompt
    assert "If you describe gameplay, navigation, game state, or fictional actions, the answer fails" in rendered.system_prompt
    assert "Primary division:" in rendered.system_prompt
    assert "Supporting divisions:" in rendered.system_prompt
    assert "debug the nostdrec recruit screen issue" in rendered.user_prompt


def test_first_officer_prompt_lists_allowed_divisions_and_forbids_generic_names() -> None:
    rendered = render_prompt_profile("first_officer_triage", {"mission": "route a mission"})

    for division in [
        "Command Division",
        "Engineering Division",
        "Computer Core / Archives",
        "Tactical / Safety",
        "Science / Game Intelligence",
        "Modding Division",
        "Design Bureau",
    ]:
        assert division in rendered.system_prompt
    assert "Use only these exact division names" in rendered.system_prompt
    assert "Software Engineering" in rendered.system_prompt
    assert "Quality Assurance" in rendered.system_prompt
    assert "Game Developer" in rendered.system_prompt
    assert "Modding Support" in rendered.system_prompt
    assert "CoE5 Mod Development" in rendered.system_prompt
    assert "If you output a division name not in the allowed list, the answer fails" in rendered.system_prompt


def test_engineering_prompt_forbids_invented_modules_and_gameplay() -> None:
    rendered = render_prompt_profile("engineering_test_design", {"task": "Suggest one route unit test."})

    assert "If actual module names, import paths, or file paths are not provided, do not invent them" in rendered.system_prompt
    assert "focus on Starship routing behavior, not game simulation" in rendered.system_prompt
    assert "Do not invent imports or modules unless provided" in rendered.system_prompt
    assert "If you invent project modules, describe gameplay, or claim to inspect files not provided, the answer fails" in rendered.system_prompt


def test_archives_prompt_requires_authority_and_current_state_distinction() -> None:
    rendered = render_prompt_profile("archives_continuity", {"context": "WorldBox Xianni source confusion"})

    assert "authority separation" in rendered.system_prompt
    assert "stale-context warnings" in rendered.system_prompt
    assert "Distinguish verified context from inferred context" in rendered.system_prompt
    assert "Current-vs-deprecated risk:" in rendered.system_prompt


def test_model_evaluation_prompt_blocks_over_promotion() -> None:
    rendered = render_prompt_profile("model_evaluation", {"observations": "Callable, slow, weak first response."})

    assert "Do not over-promote a model based on one test" in rendered.system_prompt
    assert "Latency and context window matter" in rendered.system_prompt
    assert "A model can be callable but not trusted" in rendered.system_prompt
    assert "Human judgment needed:" in rendered.system_prompt
