from __future__ import annotations

from dataclasses import asdict, dataclass


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
    ),
    TIER_STANDARD: TierConfig(
        base_url=None,
        sensory_model="claude-3-5-haiku-20241022",
        reason_model="claude-sonnet-4-6",
    ),
    TIER_ENHANCED: TierConfig(
        base_url=None,
        sensory_model="claude-3-5-haiku-20241022",
        reason_model="claude-opus-4-6",
    ),
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_tier_config(tier: int) -> dict:
    """Return the TierConfig for the given tier as a plain dict."""
    try:
        tier_number = int(tier)
    except (TypeError, ValueError):
        tier_number = DEFAULT_TIER
    return asdict(TIERS.get(tier_number, TIERS[DEFAULT_TIER]))


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
