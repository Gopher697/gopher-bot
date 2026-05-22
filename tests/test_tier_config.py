from __future__ import annotations


def test_tier_deterministic_is_zero():
    from coordinators.tier_config import TIER_DETERMINISTIC

    assert TIER_DETERMINISTIC == 0


def test_tier_local_is_one():
    from coordinators.tier_config import TIER_LOCAL

    assert TIER_LOCAL == 1


def test_tier_standard_is_two():
    from coordinators.tier_config import TIER_STANDARD

    assert TIER_STANDARD == 2


def test_tier_enhanced_is_three():
    from coordinators.tier_config import TIER_ENHANCED

    assert TIER_ENHANCED == 3


def test_default_tier_is_standard():
    from coordinators.tier_config import DEFAULT_TIER, TIER_STANDARD

    assert DEFAULT_TIER == TIER_STANDARD


def test_shutdown_tier_is_local():
    from coordinators.tier_config import SHUTDOWN_TIER, TIER_LOCAL

    assert SHUTDOWN_TIER == TIER_LOCAL


def test_shutdown_budget_fraction_between_zero_and_one():
    from coordinators.tier_config import SHUTDOWN_BUDGET_FRACTION

    assert 0.0 < SHUTDOWN_BUDGET_FRACTION <= 1.0


def test_get_tier_name_deterministic():
    from coordinators.tier_config import TIER_DETERMINISTIC, get_tier_name

    assert get_tier_name(TIER_DETERMINISTIC) == "deterministic"


def test_get_tier_name_local():
    from coordinators.tier_config import TIER_LOCAL, get_tier_name

    assert get_tier_name(TIER_LOCAL) == "local"


def test_get_tier_name_standard():
    from coordinators.tier_config import TIER_STANDARD, get_tier_name

    assert get_tier_name(TIER_STANDARD) == "standard"


def test_get_tier_name_enhanced():
    from coordinators.tier_config import TIER_ENHANCED, get_tier_name

    assert get_tier_name(TIER_ENHANCED) == "enhanced"


def test_get_tier_name_unknown():
    from coordinators.tier_config import get_tier_name

    assert get_tier_name(99) == "unknown"


def test_get_tier_name_invalid():
    from coordinators.tier_config import get_tier_name

    assert get_tier_name("bad") == "unknown"


def test_cost_deterministic_is_zero():
    from coordinators.tier_config import TIER_DETERMINISTIC, get_tier_cost_estimate

    assert get_tier_cost_estimate(TIER_DETERMINISTIC) == 0.0


def test_cost_local_is_zero():
    from coordinators.tier_config import TIER_LOCAL, get_tier_cost_estimate

    assert get_tier_cost_estimate(TIER_LOCAL) == 0.0


def test_cost_standard_positive():
    from coordinators.tier_config import TIER_STANDARD, get_tier_cost_estimate

    assert get_tier_cost_estimate(TIER_STANDARD) > 0.0


def test_cost_enhanced_greater_than_standard():
    from coordinators.tier_config import (
        TIER_ENHANCED,
        TIER_STANDARD,
        get_tier_cost_estimate,
    )

    assert get_tier_cost_estimate(TIER_ENHANCED) > get_tier_cost_estimate(TIER_STANDARD)


def test_cost_unknown_tier_returns_default():
    from coordinators.tier_config import DEFAULT_TIER, get_tier_cost_estimate

    assert get_tier_cost_estimate(99) == get_tier_cost_estimate(DEFAULT_TIER)


def test_no_cap_when_not_in_shutdown():
    from coordinators.tier_config import apply_shutdown_cap

    assert apply_shutdown_cap(3, False) == 3


def test_cap_enhanced_to_local():
    from coordinators.tier_config import SHUTDOWN_TIER, apply_shutdown_cap

    assert apply_shutdown_cap(3, True) == SHUTDOWN_TIER


def test_cap_standard_to_local():
    from coordinators.tier_config import SHUTDOWN_TIER, apply_shutdown_cap

    assert apply_shutdown_cap(2, True) == SHUTDOWN_TIER


def test_local_unchanged_in_shutdown():
    from coordinators.tier_config import apply_shutdown_cap

    assert apply_shutdown_cap(1, True) == 1


def test_deterministic_unchanged_in_shutdown():
    from coordinators.tier_config import apply_shutdown_cap

    assert apply_shutdown_cap(0, True) == 0


def test_tier_0_has_none_models():
    from coordinators.tier_config import TIER_DETERMINISTIC, get_tier_config

    config = get_tier_config(TIER_DETERMINISTIC)
    assert config["sensory_model"] is None
    assert config["reason_model"] is None


def test_tier_1_has_local_url():
    from coordinators.tier_config import TIER_LOCAL, get_tier_config

    assert get_tier_config(TIER_LOCAL)["base_url"].startswith("http://localhost")


def test_tier_2_has_no_base_url():
    from coordinators.tier_config import TIER_STANDARD, get_tier_config

    assert get_tier_config(TIER_STANDARD)["base_url"] is None


def test_unknown_tier_returns_default():
    from coordinators.tier_config import DEFAULT_TIER, get_tier_config

    assert get_tier_config(99) == get_tier_config(DEFAULT_TIER)


def test_fallbacks_are_lists():
    from coordinators.tier_config import TIERS

    for config in TIERS.values():
        assert isinstance(config.sensory_fallbacks, list)
        assert isinstance(config.reason_fallbacks, list)


def test_deterministic_tier_has_no_fallbacks():
    from coordinators.tier_config import TIER_DETERMINISTIC, TIERS

    config = TIERS[TIER_DETERMINISTIC]
    assert config.sensory_fallbacks == []
    assert config.reason_fallbacks == []


def test_known_providers_has_required_keys():
    from coordinators.tier_config import KNOWN_PROVIDERS

    for provider in KNOWN_PROVIDERS.values():
        assert "models_endpoint" in provider
        assert "config_key" in provider
