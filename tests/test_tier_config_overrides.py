"""Tests for user-configurable model overrides in tier_config."""
from __future__ import annotations

import sys
import types
from unittest.mock import patch

import coordinators.tier_config as tc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_config(**kwargs):
    """Return a minimal fake world_models.config module with given attributes."""
    mod = types.ModuleType("world_models.config")
    for k, v in kwargs.items():
        setattr(mod, k, v)
    return mod


# ---------------------------------------------------------------------------
# _get_config_override
# ---------------------------------------------------------------------------

class TestGetConfigOverride:
    def test_returns_default_when_import_fails(self):
        with patch.dict(sys.modules, {"world_models": None, "world_models.config": None}):
            result = tc._get_config_override("TIER_LOCAL_REASON_MODEL", "default-model")
        assert result == "default-model"

    def test_returns_default_when_attr_missing(self):
        fake = _fake_config()
        with patch.dict(sys.modules, {"world_models.config": fake}):
            result = tc._get_config_override("TIER_LOCAL_REASON_MODEL", "default-model")
        assert result == "default-model"

    def test_returns_default_when_attr_is_none(self):
        fake = _fake_config(TIER_LOCAL_REASON_MODEL=None)
        with patch.dict(sys.modules, {"world_models.config": fake}):
            result = tc._get_config_override("TIER_LOCAL_REASON_MODEL", "default-model")
        assert result == "default-model"

    def test_returns_default_when_attr_is_empty_string(self):
        fake = _fake_config(TIER_LOCAL_REASON_MODEL="   ")
        with patch.dict(sys.modules, {"world_models.config": fake}):
            result = tc._get_config_override("TIER_LOCAL_REASON_MODEL", "default-model")
        assert result == "default-model"

    def test_returns_override_when_set(self):
        fake = _fake_config(TIER_LOCAL_REASON_MODEL="my-custom-model")
        with patch.dict(sys.modules, {"world_models.config": fake}):
            result = tc._get_config_override("TIER_LOCAL_REASON_MODEL", "default-model")
        assert result == "my-custom-model"


# ---------------------------------------------------------------------------
# get_tier_config -- override application
# ---------------------------------------------------------------------------

class TestGetTierConfigOverrides:
    def _config_with(self, **kwargs):
        fake = _fake_config(**kwargs)
        return patch.dict(sys.modules, {"world_models.config": fake})

    def test_local_reason_override_applied(self):
        with self._config_with(TIER_LOCAL_REASON_MODEL="llama3-custom"):
            cfg = tc.get_tier_config(tc.TIER_LOCAL)
        assert cfg["reason_model"] == "llama3-custom"

    def test_local_sensory_override_applied(self):
        with self._config_with(TIER_LOCAL_SENSORY_MODEL="phi3-mini"):
            cfg = tc.get_tier_config(tc.TIER_LOCAL)
        assert cfg["sensory_model"] == "phi3-mini"

    def test_standard_reason_override_applied(self):
        with self._config_with(TIER_STANDARD_REASON_MODEL="gpt-4o"):
            cfg = tc.get_tier_config(tc.TIER_STANDARD)
        assert cfg["reason_model"] == "gpt-4o"

    def test_enhanced_reason_override_applied(self):
        with self._config_with(TIER_ENHANCED_REASON_MODEL="gpt-4o"):
            cfg = tc.get_tier_config(tc.TIER_ENHANCED)
        assert cfg["reason_model"] == "gpt-4o"

    def test_none_override_uses_default(self):
        with self._config_with(TIER_LOCAL_REASON_MODEL=None):
            cfg = tc.get_tier_config(tc.TIER_LOCAL)
        assert cfg["reason_model"] == "qwen3.5"

    def test_missing_override_uses_default(self):
        with self._config_with():
            cfg = tc.get_tier_config(tc.TIER_LOCAL)
        assert cfg["reason_model"] == "qwen3.5"
        assert cfg["sensory_model"] == "qwen2.5-3b-instruct"

    def test_deterministic_tier_unaffected(self):
        with self._config_with(TIER_LOCAL_REASON_MODEL="should-not-apply"):
            cfg = tc.get_tier_config(tc.TIER_DETERMINISTIC)
        assert cfg["reason_model"] is None
        assert cfg["sensory_model"] is None

    def test_only_specified_field_overridden(self):
        """Overriding reason_model should not affect sensory_model."""
        with self._config_with(TIER_LOCAL_REASON_MODEL="custom-reason"):
            cfg = tc.get_tier_config(tc.TIER_LOCAL)
        assert cfg["reason_model"] == "custom-reason"
        assert cfg["sensory_model"] == "qwen2.5-3b-instruct"

    def test_invalid_tier_falls_back_to_default_tier(self):
        with self._config_with():
            cfg = tc.get_tier_config(999)
        assert cfg["reason_model"] is not None
