from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


REQUIRED_FIELDS: dict[str, list[str]] = {
    "first_officer_triage": [
        "Primary division",
        "Supporting divisions",
        "Risk flags",
        "Specialist recommended",
        "One-sentence reason",
    ],
    "engineering_test_design": ["Test intent", "Assertions", "Notes"],
    "archives_continuity": [
        "Authority source needed",
        "Current-vs-deprecated risk",
        "Suggested next context to inspect",
        "One-sentence handoff note",
    ],
    "model_evaluation": [
        "Suggested role",
        "Use cases",
        "Not suitable for",
        "Retest needed",
        "Human judgment needed",
    ],
}

GAMEPLAY_DRIFT_TERMS = [
    "gameplay",
    "player",
    "game state",
    "navigate",
    "map route",
    "pathfinding",
    "class/race selection",
]

STRUCTURE_TERMS = [
    "module",
    "import",
    "class name",
    "function name",
    "file path",
    "package",
]

GENERIC_NON_STARSHIP_TERMS = [
    "Software Engineering",
    "QA",
    "Quality Assurance",
    "Game Developer",
    "Mod Development",
]

NONE_VALUES = {"none", "n/a", "not applicable", ""}


@dataclass(frozen=True)
class CrewOutputValidation:
    schema_valid: bool
    division_vocabulary_valid: str
    warnings: list[str]
    missing_required_fields: list[str]
    invalid_divisions: list[str]
    trust_gate: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_valid": self.schema_valid,
            "division_vocabulary_valid": self.division_vocabulary_valid,
            "warnings": self.warnings,
            "missing_required_fields": self.missing_required_fields,
            "invalid_divisions": self.invalid_divisions,
            "trust_gate": self.trust_gate,
            "human_review_required": True,
        }


def allowed_divisions_from_registry(registry: dict[str, Any]) -> list[str]:
    stations = registry.get("stations")
    if not isinstance(stations, dict):
        return []
    divisions: list[str] = []
    for station in stations.values():
        if isinstance(station, dict):
            name = station.get("division_name")
            if isinstance(name, str) and name.strip() and name not in divisions:
                divisions.append(name.strip())
    return divisions


def validate_crew_output(
    *,
    prompt_profile: str,
    response_text: str,
    prompt_context: str,
    allowed_divisions: list[str],
) -> CrewOutputValidation:
    missing_fields = missing_required_fields(prompt_profile, response_text)
    warnings: list[str] = []
    invalid_divisions: list[str] = []

    if missing_fields:
        warnings.append("missing_required_field")

    division_vocabulary_valid = "not_applicable"
    if prompt_profile == "first_officer_triage":
        invalid_divisions = find_invalid_first_officer_divisions(response_text, allowed_divisions)
        division_vocabulary_valid = "no" if invalid_divisions else "yes"
        if invalid_divisions:
            warnings.append("invalid_division")

    if contains_any_term(response_text, GAMEPLAY_DRIFT_TERMS):
        warnings.append("gameplay_drift")

    if contains_structure_term_not_in_context(response_text, prompt_context):
        warnings.append("invented_structure_possible")

    if contains_any_term(response_text, GENERIC_NON_STARSHIP_TERMS):
        if "invalid_division" not in warnings and prompt_profile == "first_officer_triage":
            warnings.append("invalid_division")
        elif prompt_profile != "first_officer_triage":
            warnings.append("invented_structure_possible")

    schema_valid = not missing_fields
    trust_gate = "fail" if warnings or not schema_valid or division_vocabulary_valid == "no" else "human_review_required"
    return CrewOutputValidation(
        schema_valid=schema_valid,
        division_vocabulary_valid=division_vocabulary_valid,
        warnings=sorted(dict.fromkeys(warnings)),
        missing_required_fields=missing_fields,
        invalid_divisions=invalid_divisions,
        trust_gate=trust_gate,
    )


def missing_required_fields(prompt_profile: str, response_text: str) -> list[str]:
    required = REQUIRED_FIELDS.get(prompt_profile, [])
    return [field for field in required if not has_label(response_text, field)]


def has_label(text: str, label: str) -> bool:
    return re.search(rf"(?im)^\s*[-*]?\s*{re.escape(label)}\s*:", text) is not None


def extract_label_value(text: str, label: str) -> str:
    match = re.search(rf"(?im)^\s*[-*]?\s*{re.escape(label)}\s*:\s*(.+?)\s*$", text)
    return match.group(1).strip() if match else ""


def find_invalid_first_officer_divisions(response_text: str, allowed_divisions: list[str]) -> list[str]:
    allowed = set(allowed_divisions)
    invalid: list[str] = []
    primary = extract_label_value(response_text, "Primary division")
    if primary and primary not in allowed:
        invalid.append(primary)

    supporting = extract_label_value(response_text, "Supporting divisions")
    if supporting.casefold() not in NONE_VALUES:
        for value in split_division_values(supporting):
            if value not in allowed and value.casefold() not in NONE_VALUES:
                invalid.append(value)
    return list(dict.fromkeys(invalid))


def split_division_values(value: str) -> list[str]:
    normalized = value.replace(" and ", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def contains_any_term(text: str, terms: list[str]) -> bool:
    lowered = text.casefold()
    return any(term.casefold() in lowered for term in terms)


def contains_structure_term_not_in_context(response_text: str, prompt_context: str) -> bool:
    lowered_context = prompt_context.casefold()
    lowered_response = response_text.casefold()
    for term in STRUCTURE_TERMS:
        if term.casefold() in lowered_response and term.casefold() not in lowered_context:
            return True
    return False
