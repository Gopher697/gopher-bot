from __future__ import annotations

import importlib
from dataclasses import asdict, dataclass, field


# ---------------------------------------------------------------------------
# Tier names — used for logging and packet annotation
# ---------------------------------------------------------------------------

TIER_DETERMINISTIC = 0   # No LLM call — pure Python / deterministic response
TIER_LOCAL         = 1   # Local LLM (localhost; zero marginal cost)
TIER_STANDARD      = 2   # Cloud Haiku + Sonnet  (default)
TIER_ENHANCED      = 3   # Cloud Haiku + Opus    (high-stakes / complex)

DEFAULT_TIER = TIER_STANDARD

# In shutdown mode, tier is capped at this value.
SHUTDOWN_TIER = TIER_LOCAL

# Budget fraction that auto-triggers shutdown mode in Drive.
SHUTDOWN_BUDGET_FRACTION = 0.95

TIER_NAMES: dict[int, str] = {
    TIER_DETERMINISTIC: "deterministic",
    TIER_LOCAL:         "local",
    TIER_STANDARD:      "standard",
    TIER_ENHANCED:      "enhanced",
}

# Estimated USD cost per LLM call at each tier (used by Drive for budget tracking).
TIER_COST_ESTIMATES: dict[int, float] = {
    TIER_DETERMINISTIC: 0.0,
    TIER_LOCAL:         0.0,
    TIER_STANDARD:      0.01,
    TIER_ENHANCED:      0.10,
}


# ---------------------------------------------------------------------------
# TierConfig — model assignments per tier
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TierConfig:
    base_url: str | None        # None = Anthropic cloud; str = local OpenAI-compat endpoint
    sensory_model: str | None   # None for TIER_DETERMINISTIC (no LLM)
    reason_model: str | None    # None for TIER_DETERMINISTIC (no LLM)
    sensory_fallbacks: list[str] = field(default_factory=list)
    reason_fallbacks: list[str] = field(default_factory=list)
    provider: str = "anthropic"
    sensory_provider: str | None = None
    reason_provider: str | None = None


KNOWN_PROVIDERS: dict[str, dict] = {
    "anthropic": {
        "models_endpoint": "https://api.anthropic.com/v1/models",
        "auth_header": "x-api-key",
        "config_key": "ANTHROPIC_API_KEY",
    },
    "openai": {
        "models_endpoint": "https://api.openai.com/v1/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "config_key": "OPENAI_API_KEY",
    },
    "deepseek": {
        "models_endpoint": "https://api.deepseek.com/v1/models",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "config_key": "DEEPSEEK_API_KEY",
    },
    "lm_studio": {
        "models_endpoint": "http://localhost:1234/v1/models",
        "auth_header": None,
        "config_key": "LM_STUDIO_API_KEY",
    },
}


TIERS: dict[int, TierConfig] = {
    TIER_DETERMINISTIC: TierConfig(
        base_url=None,
        sensory_model=None,
        reason_model=None,
    ),
    TIER_LOCAL: TierConfig(
        base_url="http://localhost:1234/v1",
        sensory_model="qwen2.5-3b-instruct",
        reason_model="qwen3.5",
        provider="lm_studio",
        sensory_provider="lm_studio",
        reason_provider="lm_studio",
    ),
    TIER_STANDARD: TierConfig(
        base_url=None,
        sensory_model="claude-haiku-4-5-20251001",
        reason_model="claude-sonnet-4-6",
        reason_fallbacks=["claude-haiku-4-5-20251001"],
    ),
    TIER_ENHANCED: TierConfig(
        base_url=None,
        sensory_model="claude-haiku-4-5-20251001",
        reason_model="claude-opus-4-6",
        reason_fallbacks=["claude-sonnet-4-6"],
    ),
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def _get_config_override(attr: str, default: str | None) -> str | None:
    """
    Safely read an optional model override from world_models.config.

    Returns *default* if config cannot be imported, the attribute is missing,
    or the attribute is None/blank.
    """
    try:
        config = importlib.import_module("world_models.config")
        value = getattr(config, attr, None)
        return value if isinstance(value, str) and value.strip() else default
    except Exception:
        return default


def get_tier_config(tier: int) -> dict:
    """Return the TierConfig for the given tier as a plain dict.

    Model assignments can be overridden per-tier via optional fields in
    world_models/config.py. Any field set to None or absent falls back to the
    hardcoded default.
    """
    try:
        tier_number = int(tier)
    except (TypeError, ValueError):
        tier_number = DEFAULT_TIER

    cfg = asdict(TIERS.get(tier_number, TIERS[DEFAULT_TIER]))

    override_map: dict[int, tuple[str, str]] = {
        TIER_LOCAL: ("TIER_LOCAL_REASON_MODEL", "TIER_LOCAL_SENSORY_MODEL"),
        TIER_STANDARD: ("TIER_STANDARD_REASON_MODEL", "TIER_STANDARD_SENSORY_MODEL"),
        TIER_ENHANCED: ("TIER_ENHANCED_REASON_MODEL", "TIER_ENHANCED_SENSORY_MODEL"),
    }

    if tier_number in override_map:
        reason_key, sensory_key = override_map[tier_number]
        cfg["reason_model"] = _get_config_override(reason_key, cfg["reason_model"])
        cfg["sensory_model"] = _get_config_override(sensory_key, cfg["sensory_model"])

    return cfg


def get_tier_name(tier: int) -> str:
    """Return the human-readable name for a tier number."""
    try:
        return TIER_NAMES.get(int(tier), "unknown")
    except (TypeError, ValueError):
        return "unknown"


def get_tier_cost_estimate(tier: int) -> float:
    """Return the estimated USD cost per LLM call at this tier."""
    try:
        return TIER_COST_ESTIMATES.get(int(tier), TIER_COST_ESTIMATES[DEFAULT_TIER])
    except (TypeError, ValueError):
        return TIER_COST_ESTIMATES[DEFAULT_TIER]


def apply_shutdown_cap(tier: int, shutdown_mode: bool) -> int:
    """
    If shutdown_mode is True, cap the tier at SHUTDOWN_TIER.

    This prevents expensive cloud LLM calls when the budget is near ceiling.
    If shutdown_mode is False, returns tier unchanged.
    """
    if not shutdown_mode:
        return int(tier)
    return min(int(tier), SHUTDOWN_TIER)
