from __future__ import annotations

from dataclasses import asdict, dataclass


DEFAULT_TIER = 2


@dataclass(frozen=True)
class TierConfig:
    base_url: str | None
    sensory_model: str
    reason_model: str


TIERS = {
    1: TierConfig(
        base_url="http://localhost:1234/v1",
        sensory_model="qwen2.5-3b-instruct",
        reason_model="qwen3.5",
    ),
    2: TierConfig(
        base_url=None,
        sensory_model="claude-3-5-haiku-20241022",
        reason_model="claude-sonnet-4-6",
    ),
    3: TierConfig(
        base_url=None,
        sensory_model="claude-3-5-haiku-20241022",
        reason_model="claude-opus-4-6",
    ),
}


def get_tier_config(tier: int) -> dict:
    try:
        tier_number = int(tier)
    except (TypeError, ValueError):
        tier_number = DEFAULT_TIER

    return asdict(TIERS.get(tier_number, TIERS[DEFAULT_TIER]))
