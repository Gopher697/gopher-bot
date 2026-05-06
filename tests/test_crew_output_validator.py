from __future__ import annotations

from pathlib import Path

from starship_command.crew_output_validator import (
    allowed_divisions_from_registry,
    validate_crew_output,
)
from starship_command.starship_core import load_registry


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "starship_command" / "command_registry.yaml"


def allowed_divisions() -> list[str]:
    return allowed_divisions_from_registry(load_registry(REGISTRY_PATH))


def test_allowed_divisions_load_from_registry() -> None:
    divisions = allowed_divisions()

    assert divisions == [
        "Command Division",
        "Engineering Division",
        "Computer Core / Archives",
        "Tactical / Safety",
        "Science / Game Intelligence",
        "Modding Division",
        "Design Bureau",
    ]


def test_first_officer_valid_output_passes_schema_and_division_vocabulary() -> None:
    validation = validate_crew_output(
        prompt_profile="first_officer_triage",
        response_text=(
            "Primary division: Engineering Division\n"
            "Supporting divisions: Modding Division\n"
            "Risk flags: None\n"
            "Specialist recommended: yes\n"
            "One-sentence reason: This is a code debugging mission with mod-specific context."
        ),
        prompt_context="debug the nostdrec recruit screen issue in the CoE5 mod",
        allowed_divisions=allowed_divisions(),
    )

    assert validation.schema_valid is True
    assert validation.division_vocabulary_valid == "yes"
    assert validation.warnings == []
    assert validation.trust_gate == "human_review_required"


def test_first_officer_invalid_divisions_are_flagged() -> None:
    validation = validate_crew_output(
        prompt_profile="first_officer_triage",
        response_text=(
            "Primary division: Software Engineering\n"
            "Supporting divisions: Quality Assurance, Game Developer\n"
            "Risk flags: None\n"
            "Specialist recommended: yes\n"
            "One-sentence reason: Generic coding roles were chosen."
        ),
        prompt_context="debug the nostdrec recruit screen issue in the CoE5 mod",
        allowed_divisions=allowed_divisions(),
    )

    assert validation.schema_valid is True
    assert validation.division_vocabulary_valid == "no"
    assert "invalid_division" in validation.warnings
    assert validation.invalid_divisions == ["Software Engineering", "Quality Assurance", "Game Developer"]
    assert validation.trust_gate == "fail"


def test_required_schema_detection_for_all_prompt_profiles() -> None:
    cases = {
        "first_officer_triage": "Primary division: Engineering Division",
        "engineering_test_design": "Test intent: Verify routing.",
        "archives_continuity": "Authority source needed: PROJECT.md",
        "model_evaluation": "Suggested role: fast triage candidate",
    }

    for profile, response in cases.items():
        validation = validate_crew_output(
            prompt_profile=profile,
            response_text=response,
            prompt_context="minimal context",
            allowed_divisions=allowed_divisions(),
        )
        assert validation.schema_valid is False
        assert "missing_required_field" in validation.warnings
        assert validation.trust_gate == "fail"


def test_gameplay_navigation_drift_warning() -> None:
    validation = validate_crew_output(
        prompt_profile="first_officer_triage",
        response_text=(
            "Primary division: Engineering Division\n"
            "Supporting divisions: None\n"
            "Risk flags: None\n"
            "Specialist recommended: no\n"
            "One-sentence reason: The player must navigate the recruit screen."
        ),
        prompt_context="debug the nostdrec recruit screen issue in the CoE5 mod",
        allowed_divisions=allowed_divisions(),
    )

    assert "gameplay_drift" in validation.warnings
    assert validation.trust_gate == "fail"


def test_invented_structure_warning_when_structure_terms_are_absent_from_context() -> None:
    validation = validate_crew_output(
        prompt_profile="engineering_test_design",
        response_text=(
            "Test intent: Verify routing.\n"
            "Assertions: Engineering module remains primary.\n"
            "Notes: Do not modify files."
        ),
        prompt_context="Suggest one Starship Command routing unit test.",
        allowed_divisions=allowed_divisions(),
    )

    assert validation.schema_valid is True
    assert validation.division_vocabulary_valid == "not_applicable"
    assert "invented_structure_possible" in validation.warnings
    assert validation.trust_gate == "fail"


def test_structure_terms_allowed_when_present_in_context() -> None:
    validation = validate_crew_output(
        prompt_profile="engineering_test_design",
        response_text=(
            "Test intent: Verify routing.\n"
            "Assertions: The module routes correctly.\n"
            "Notes: Module language was provided."
        ),
        prompt_context="The provided context mentions module routing.",
        allowed_divisions=allowed_divisions(),
    )

    assert "invented_structure_possible" not in validation.warnings
