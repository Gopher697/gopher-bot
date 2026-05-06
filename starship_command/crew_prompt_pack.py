from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Any

import yaml


PROMPT_PACK_PATH = Path(__file__).with_name("crew_prompt_pack.yaml")


class CrewPromptPackError(RuntimeError):
    """Raised when a crew prompt profile cannot be loaded or rendered."""


@dataclass(frozen=True)
class CrewPromptProfile:
    profile_id: str
    purpose: str
    system_prompt: str
    user_prompt_template: str


@dataclass(frozen=True)
class RenderedPrompt:
    profile_id: str
    system_prompt: str
    user_prompt: str


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CrewPromptPackError(f"crew prompt profile {field_name} must be a non-empty string")
    return value.strip()


def load_prompt_pack(prompt_pack_path: Path = PROMPT_PACK_PATH) -> dict[str, CrewPromptProfile]:
    with prompt_pack_path.open("r", encoding="utf-8") as handle:
        raw_pack = yaml.safe_load(handle)
    if not isinstance(raw_pack, dict):
        raise CrewPromptPackError("crew prompt pack must be a mapping")

    raw_profiles = raw_pack.get("profiles")
    if not isinstance(raw_profiles, dict) or not raw_profiles:
        raise CrewPromptPackError("crew prompt pack must define profiles")

    profiles: dict[str, CrewPromptProfile] = {}
    for profile_id, raw_profile in raw_profiles.items():
        if not isinstance(profile_id, str) or not profile_id.strip():
            raise CrewPromptPackError("crew prompt profile id must be a non-empty string")
        if not isinstance(raw_profile, dict):
            raise CrewPromptPackError(f"crew prompt profile {profile_id} must be a mapping")
        profiles[profile_id] = CrewPromptProfile(
            profile_id=profile_id,
            purpose=_string(raw_profile.get("purpose"), f"{profile_id}.purpose"),
            system_prompt=_string(raw_profile.get("system_prompt"), f"{profile_id}.system_prompt"),
            user_prompt_template=_string(
                raw_profile.get("user_prompt_template"),
                f"{profile_id}.user_prompt_template",
            ),
        )
    return profiles


def get_prompt_profile(
    profile_id: str,
    prompt_pack_path: Path = PROMPT_PACK_PATH,
) -> CrewPromptProfile:
    profiles = load_prompt_pack(prompt_pack_path)
    try:
        return profiles[profile_id]
    except KeyError as exc:
        raise CrewPromptPackError(f"Unknown crew prompt profile: {profile_id}") from exc


def render_prompt_profile(
    profile_id: str,
    variables: dict[str, Any] | None = None,
    prompt_pack_path: Path = PROMPT_PACK_PATH,
) -> RenderedPrompt:
    profile = get_prompt_profile(profile_id, prompt_pack_path)
    safe_variables = {key: "" if value is None else str(value) for key, value in (variables or {}).items()}
    return RenderedPrompt(
        profile_id=profile.profile_id,
        system_prompt=profile.system_prompt,
        user_prompt=Template(profile.user_prompt_template).safe_substitute(safe_variables).strip(),
    )
