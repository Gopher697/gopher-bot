"""Tests for AVAILABLE_MODELS intelligent model selection."""
from __future__ import annotations

import sys
import types
from unittest.mock import patch

import coordinators.archivist as archivist_mod
import coordinators.tier_config as tc


def _fake_config(**kwargs):
    mod = types.ModuleType("world_models.config")
    for k, v in kwargs.items():
        setattr(mod, k, v)
    return mod


def _with_config(**kwargs):
    fake = _fake_config(**kwargs)
    return patch.dict(sys.modules, {"world_models.config": fake})


# ---------------------------------------------------------------------------
# _select_from_available
# ---------------------------------------------------------------------------

class TestSelectFromAvailable:
    def test_returns_none_when_available_models_empty(self):
        with _with_config(AVAILABLE_MODELS=[]):
            result = tc._select_from_available(tc.TIER_LOCAL, "reason")
        assert result is None

    def test_returns_none_when_available_models_unset(self):
        with _with_config():
            result = tc._select_from_available(tc.TIER_LOCAL, "reason")
        assert result is None

    def test_selects_local_reason_model(self):
        models = [
            {"name": "qwen3.5", "provider": "lm_studio", "capability": "local"},
            {"name": "qwen2.5-3b-instruct", "provider": "lm_studio", "capability": "local-fast"},
        ]
        with _with_config(AVAILABLE_MODELS=models):
            result = tc._select_from_available(tc.TIER_LOCAL, "reason")
        assert result == "qwen3.5"

    def test_selects_local_fast_for_sensory(self):
        models = [
            {"name": "qwen3.5", "provider": "lm_studio", "capability": "local"},
            {"name": "qwen2.5-3b-instruct", "provider": "lm_studio", "capability": "local-fast"},
        ]
        with _with_config(AVAILABLE_MODELS=models):
            result = tc._select_from_available(tc.TIER_LOCAL, "sensory")
        assert result == "qwen2.5-3b-instruct"

    def test_selects_standard_reason_model(self):
        models = [
            {"name": "claude-sonnet-4-6", "provider": "anthropic", "capability": "standard"},
            {"name": "claude-haiku-4-5-20251001", "provider": "anthropic", "capability": "fast"},
        ]
        with _with_config(AVAILABLE_MODELS=models):
            result = tc._select_from_available(tc.TIER_STANDARD, "reason")
        assert result == "claude-sonnet-4-6"

    def test_selects_fast_for_standard_sensory(self):
        models = [
            {"name": "claude-sonnet-4-6", "provider": "anthropic", "capability": "standard"},
            {"name": "claude-haiku-4-5-20251001", "provider": "anthropic", "capability": "fast"},
        ]
        with _with_config(AVAILABLE_MODELS=models):
            result = tc._select_from_available(tc.TIER_STANDARD, "sensory")
        assert result == "claude-haiku-4-5-20251001"

    def test_falls_back_within_preference_order(self):
        models = [
            {"name": "claude-opus-4-6", "provider": "anthropic", "capability": "capable"},
        ]
        with _with_config(AVAILABLE_MODELS=models):
            result = tc._select_from_available(tc.TIER_STANDARD, "reason")
        assert result == "claude-opus-4-6"

    def test_filters_by_provider(self):
        models = [
            {"name": "qwen3.5", "provider": "lm_studio", "capability": "standard"},
        ]
        with _with_config(AVAILABLE_MODELS=models):
            result = tc._select_from_available(tc.TIER_STANDARD, "reason")
        assert result is None

    def test_ignores_invalid_entries(self):
        models = [
            "not-a-dict",
            {"name": "", "provider": "lm_studio", "capability": "local"},
            {"name": None, "provider": "lm_studio", "capability": "local"},
            {"name": "qwen3.5", "provider": "lm_studio", "capability": "local"},
        ]
        with _with_config(AVAILABLE_MODELS=models):
            result = tc._select_from_available(tc.TIER_LOCAL, "reason")
        assert result == "qwen3.5"

    def test_first_match_wins(self):
        models = [
            {"name": "model-a", "provider": "lm_studio", "capability": "local"},
            {"name": "model-b", "provider": "lm_studio", "capability": "local"},
        ]
        with _with_config(AVAILABLE_MODELS=models):
            result = tc._select_from_available(tc.TIER_LOCAL, "reason")
        assert result == "model-a"


# ---------------------------------------------------------------------------
# get_tier_config — priority order
# ---------------------------------------------------------------------------

class TestGetTierConfigPriority:
    def test_available_models_overrides_hardcoded_default(self):
        models = [
            {"name": "custom-local", "provider": "lm_studio", "capability": "local"},
        ]
        with _with_config(AVAILABLE_MODELS=models):
            cfg = tc.get_tier_config(tc.TIER_LOCAL)
        assert cfg["reason_model"] == "custom-local"

    def test_per_field_override_beats_available_models(self):
        models = [
            {"name": "from-available", "provider": "lm_studio", "capability": "local"},
        ]
        with _with_config(AVAILABLE_MODELS=models, TIER_LOCAL_REASON_MODEL="from-field"):
            cfg = tc.get_tier_config(tc.TIER_LOCAL)
        assert cfg["reason_model"] == "from-field"

    def test_hardcoded_default_used_when_nothing_configured(self):
        with _with_config(AVAILABLE_MODELS=[]):
            cfg = tc.get_tier_config(tc.TIER_LOCAL)
        assert cfg["reason_model"] == "qwen3.5"

    def test_deterministic_tier_unaffected(self):
        models = [
            {"name": "custom-local", "provider": "lm_studio", "capability": "local"},
        ]
        with _with_config(AVAILABLE_MODELS=models):
            cfg = tc.get_tier_config(tc.TIER_DETERMINISTIC)
        assert cfg["reason_model"] is None


# ---------------------------------------------------------------------------
# get_archivist_model_from_available
# ---------------------------------------------------------------------------

class TestGetArchivistModelFromAvailable:
    def test_returns_local_fast_for_archivist(self):
        models = [
            {"name": "qwen2.5-3b-instruct", "provider": "lm_studio", "capability": "local-fast"},
        ]
        with _with_config(AVAILABLE_MODELS=models):
            result = tc.get_archivist_model_from_available()
        assert result == "qwen2.5-3b-instruct"

    def test_returns_none_when_no_local_models(self):
        models = [
            {"name": "claude-sonnet-4-6", "provider": "anthropic", "capability": "standard"},
        ]
        with _with_config(AVAILABLE_MODELS=models):
            result = tc.get_archivist_model_from_available()
        assert result is None


class TestArchivistAvailableModelPriority:
    def test_archivist_uses_available_models_before_default(self):
        models = [
            {"name": "custom-archivist", "provider": "lm_studio", "capability": "local-fast"},
        ]
        with _with_config(AVAILABLE_MODELS=models):
            result = archivist_mod._get_archivist_model()
        assert result == "custom-archivist"

    def test_archivist_per_field_override_beats_available_models(self):
        models = [
            {"name": "from-available", "provider": "lm_studio", "capability": "local-fast"},
        ]
        with _with_config(AVAILABLE_MODELS=models, ARCHIVIST_MODEL="from-field"):
            result = archivist_mod._get_archivist_model()
        assert result == "from-field"
