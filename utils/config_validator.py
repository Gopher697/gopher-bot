"""
config_validator.py — Sanity-check world_models/config.py values at startup.

Validates API key format (detects placeholders and obvious bad values) and
cloud model names (ensures tier_config.py references recognised model strings).
Does NOT read or repeat credential values — reports pass/warn/fail per field.

Usage:
    from utils.config_validator import validate_config
    issues = validate_config()          # returns list[ConfigIssue]
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Known-good model prefixes for each provider
# ---------------------------------------------------------------------------

#: Cloud model strings must start with one of these.
ANTHROPIC_MODEL_PREFIXES: tuple[str, ...] = (
    "claude-",
)

#: Placeholder strings that indicate an unconfigured key.
PLACEHOLDER_SUBSTRINGS: tuple[str, ...] = (
    "your-key-here",
    "your-password-here",
    "changeme",
    "placeholder",
    "example",
    "xxxx",
    "<",
    ">",
)


# ---------------------------------------------------------------------------
# Issue dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConfigIssue:
    severity: str       # "warn" | "fail"
    field: str
    detail: str


# ---------------------------------------------------------------------------
# Individual validators (operate on plain values — never log them)
# ---------------------------------------------------------------------------

def _looks_like_placeholder(value: str) -> bool:
    low = value.lower()
    return any(p in low for p in PLACEHOLDER_SUBSTRINGS)


def _check_api_key(field: str, value: Any, prefix: str) -> list[ConfigIssue]:
    """Return issues for an API key field."""
    if not value:
        return [ConfigIssue("fail", field, "empty — set a real key in world_models/config.py")]
    s = str(value)
    if _looks_like_placeholder(s):
        return [ConfigIssue("fail", field, "still set to a placeholder — replace with a real key")]
    if not s.startswith(prefix):
        return [ConfigIssue("warn", field, f"unexpected format (expected prefix {prefix!r}) — verify the key is correct")]
    return []


def _check_cloud_models() -> list[ConfigIssue]:
    """Verify that TIER_STANDARD and TIER_ENHANCED model strings look like Anthropic models."""
    issues: list[ConfigIssue] = []
    try:
        from coordinators.tier_config import TIERS, TIER_STANDARD, TIER_ENHANCED
        for tier_id in (TIER_STANDARD, TIER_ENHANCED):
            cfg = TIERS[tier_id]
            for attr in ("sensory_model", "reason_model"):
                model = getattr(cfg, attr, None)
                if model is None:
                    issues.append(ConfigIssue(
                        "fail", f"tier[{tier_id}].{attr}",
                        "None — cloud tier must have a model name"
                    ))
                    continue
                if not any(model.startswith(p) for p in ANTHROPIC_MODEL_PREFIXES):
                    issues.append(ConfigIssue(
                        "warn", f"tier[{tier_id}].{attr}",
                        f"{model!r} does not match known Anthropic model prefixes"
                    ))
    except Exception as exc:
        issues.append(ConfigIssue("fail", "tier_config", f"could not import: {exc}"))
    return issues


def _check_deterministic_tier_bypasses_llm() -> list[ConfigIssue]:
    """TIER_DETERMINISTIC must have None for both model fields."""
    try:
        from coordinators.tier_config import TIERS, TIER_DETERMINISTIC
        cfg = TIERS[TIER_DETERMINISTIC]
        issues = []
        for attr in ("sensory_model", "reason_model"):
            if getattr(cfg, attr) is not None:
                issues.append(ConfigIssue(
                    "fail", f"tier[{TIER_DETERMINISTIC}].{attr}",
                    "TIER_DETERMINISTIC must have None models — LLM would be invoked"
                ))
        return issues
    except Exception as exc:
        return [ConfigIssue("fail", "tier_config", f"could not import: {exc}")]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def validate_config(cfg: Any = None) -> list[ConfigIssue]:
    """
    Run all config sanity checks. Returns a (possibly empty) list of ConfigIssue.

    Call this at startup to surface misconfigurations before the bot starts.
    Never logs or returns credential values.

    Args:
        cfg: Optional config module to validate. If None, imports world_models.config.
             Pass a module object explicitly in tests to avoid import caching issues.
    """
    issues: list[ConfigIssue] = []

    if cfg is None:
        try:
            import world_models.config as _cfg
            cfg = _cfg
        except Exception as exc:
            return [ConfigIssue("fail", "world_models.config", f"could not import: {exc}")]

    # API keys
    issues.extend(_check_api_key(
        "ANTHROPIC_API_KEY",
        getattr(cfg, "ANTHROPIC_API_KEY", None),
        prefix="sk-ant-",
    ))

    # OPENAI_API_KEY is optional — only check format if it's present
    openai_key = getattr(cfg, "OPENAI_API_KEY", None)
    if openai_key:
        s = str(openai_key)
        if _looks_like_placeholder(s):
            issues.append(ConfigIssue(
                "warn", "OPENAI_API_KEY",
                "still set to a placeholder — clear it or replace with a real key"
            ))
        elif not s.startswith("sk-"):
            issues.append(ConfigIssue(
                "warn", "OPENAI_API_KEY",
                "unexpected format (expected prefix 'sk-') — verify the key is correct"
            ))

    neo4j_uri = getattr(cfg, "NEO4J_URI", None)
    if not neo4j_uri:
        issues.append(ConfigIssue(
            "fail", "NEO4J_URI",
            "empty — set the Neo4j connection URI in world_models/config.py"
        ))
    else:
        s = str(neo4j_uri)
        if not s.startswith(("neo4j://", "bolt://", "neo4j+s://", "bolt+s://")):
            issues.append(ConfigIssue(
                "warn", "NEO4J_URI",
                "unexpected format (expected neo4j://, bolt://, neo4j+s://, or bolt+s://)"
            ))

    neo4j_user = getattr(cfg, "NEO4J_USER", None)
    if not neo4j_user:
        issues.append(ConfigIssue(
            "fail", "NEO4J_USER",
            "empty — set the Neo4j user in world_models/config.py"
        ))

    neo4j_password = getattr(cfg, "NEO4J_PASSWORD", None)
    if not neo4j_password:
        issues.append(ConfigIssue(
            "fail", "NEO4J_PASSWORD",
            "empty — set the Neo4j password in world_models/config.py"
        ))
    else:
        s = str(neo4j_password)
        if _looks_like_placeholder(s):
            issues.append(ConfigIssue(
                "fail", "NEO4J_PASSWORD",
                "still set to a placeholder — replace with the real Neo4j password"
            ))

    lm_studio_key = getattr(cfg, "LM_STUDIO_API_KEY", None)
    if lm_studio_key:
        s = str(lm_studio_key)
        if _looks_like_placeholder(s):
            issues.append(ConfigIssue(
                "warn", "LM_STUDIO_API_KEY",
                "still set to a placeholder — clear it or replace with a real key"
            ))

    # Model names
    issues.extend(_check_cloud_models())

    # Deterministic tier must not invoke LLM
    issues.extend(_check_deterministic_tier_bypasses_llm())

    return issues
