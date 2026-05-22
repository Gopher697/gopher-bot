"""Tests for utils/config_validator.py."""
from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.config_validator import (
    ConfigIssue,
    _check_api_key,
    _check_cloud_models,
    _check_configured_models_in_registry,
    _check_deterministic_tier_bypasses_llm,
    _looks_like_placeholder,
    validate_config,
)


# ---------------------------------------------------------------------------
# Placeholder detection
# ---------------------------------------------------------------------------

class TestPlaceholderDetection:
    def test_your_key_here_is_placeholder(self):
        assert _looks_like_placeholder("your-key-here")

    def test_your_password_here_is_placeholder(self):
        assert _looks_like_placeholder("your-password-here")

    def test_changeme_is_placeholder(self):
        assert _looks_like_placeholder("changeme")

    def test_angle_bracket_is_placeholder(self):
        assert _looks_like_placeholder("<insert-key>")

    def test_real_key_prefix_is_not_placeholder(self):
        assert not _looks_like_placeholder("sk-ant-api03-realkey")

    def test_random_string_is_not_placeholder(self):
        assert not _looks_like_placeholder("abc123xyz")


# ---------------------------------------------------------------------------
# API key validation
# ---------------------------------------------------------------------------

class TestApiKeyValidation:
    def test_empty_key_is_fail(self):
        issues = _check_api_key("ANTHROPIC_API_KEY", "", prefix="sk-ant-")
        assert any(i.severity == "fail" for i in issues)

    def test_none_key_is_fail(self):
        issues = _check_api_key("ANTHROPIC_API_KEY", None, prefix="sk-ant-")
        assert any(i.severity == "fail" for i in issues)

    def test_placeholder_key_is_fail(self):
        issues = _check_api_key("ANTHROPIC_API_KEY", "your-key-here", prefix="sk-ant-")
        assert any(i.severity == "fail" for i in issues)

    def test_wrong_prefix_is_warn(self):
        issues = _check_api_key("ANTHROPIC_API_KEY", "sk-wrongprefix-abc123", prefix="sk-ant-")
        assert any(i.severity == "warn" for i in issues)

    def test_correct_prefix_no_issues(self):
        issues = _check_api_key("ANTHROPIC_API_KEY", "sk-ant-api03-realkey", prefix="sk-ant-")
        assert issues == []


# ---------------------------------------------------------------------------
# Cloud model name validation
# ---------------------------------------------------------------------------

class TestCloudModelValidation:
    def test_valid_claude_models_pass(self):
        issues = _check_cloud_models()
        # All current tier models start with "claude-" — should be no failures
        fails = [i for i in issues if i.severity == "fail"]
        assert fails == [], f"Unexpected failures: {fails}"

    def test_deterministic_tier_has_none_models(self):
        issues = _check_deterministic_tier_bypasses_llm()
        assert issues == [], f"Deterministic tier has non-None models: {issues}"


# ---------------------------------------------------------------------------
# validate_config integration (with mocked config)
# ---------------------------------------------------------------------------

def _make_fake_config(**kwargs) -> ModuleType:
    """Build a minimal fake config module for testing."""
    mod = ModuleType("world_models.config")
    defaults = {
        "NEO4J_URI": "neo4j://127.0.0.1:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "testpassword",
        "ANTHROPIC_API_KEY": "sk-ant-api03-testkey",
        "OPENAI_API_KEY": None,
    }
    defaults.update(kwargs)
    for k, v in defaults.items():
        setattr(mod, k, v)
    return mod


def _make_registry(
    known_by_provider: dict[str, list[str]] | None = None,
    unavailable_by_provider: dict[str, list[str]] | None = None,
) -> dict:
    """Build a registry shaped like world_models/model_registry.json."""
    from coordinators.tier_config import KNOWN_PROVIDERS

    known_by_provider = known_by_provider or {}
    unavailable_by_provider = unavailable_by_provider or {}
    providers = {}
    for provider in KNOWN_PROVIDERS:
        known = list(known_by_provider.get(provider, []))
        unavailable = list(unavailable_by_provider.get(provider, []))
        providers[provider] = {
            "last_discovered": "2026-05-22" if known or unavailable else None,
            "known_models": known,
            "unavailable_models": unavailable,
            "discovery_error": None,
        }
    return {
        "schema_version": 1,
        "last_updated": "2026-05-22",
        "providers": providers,
    }


def _known_models_except(target: tuple[str, str]) -> dict[str, list[str]]:
    from utils.model_registry import get_configured_models

    known_by_provider: dict[str, list[str]] = {}
    for provider, model_id in get_configured_models():
        if (provider, model_id) == target:
            continue
        known_by_provider.setdefault(provider, []).append(model_id)
    return known_by_provider


class TestValidateConfig:
    def test_clean_config_returns_no_issues(self):
        issues = validate_config(cfg=_make_fake_config())
        fails = [i for i in issues if i.severity == "fail"]
        assert fails == [], f"Unexpected failures with clean config: {fails}"

    def test_placeholder_anthropic_key_is_fail(self):
        issues = validate_config(cfg=_make_fake_config(ANTHROPIC_API_KEY="your-key-here"))
        assert any(
            i.severity == "fail" and "ANTHROPIC_API_KEY" in i.field
            for i in issues
        )

    def test_placeholder_openai_key_is_warn(self):
        issues = validate_config(cfg=_make_fake_config(OPENAI_API_KEY="your-key-here"))
        assert any(
            i.severity == "warn" and "OPENAI_API_KEY" in i.field
            for i in issues
        )

    def test_missing_anthropic_key_is_fail(self):
        issues = validate_config(cfg=_make_fake_config(ANTHROPIC_API_KEY=None))
        assert any(
            i.severity == "fail" and "ANTHROPIC_API_KEY" in i.field
            for i in issues
        )

    def test_missing_neo4j_uri_is_fail(self):
        issues = validate_config(cfg=_make_fake_config(NEO4J_URI=None))
        assert any(
            i.severity == "fail" and "NEO4J_URI" in i.field
            for i in issues
        )

    def test_missing_neo4j_user_is_fail(self):
        issues = validate_config(cfg=_make_fake_config(NEO4J_USER=""))
        assert any(
            i.severity == "fail" and "NEO4J_USER" in i.field
            for i in issues
        )

    def test_placeholder_neo4j_password_is_fail(self):
        issues = validate_config(cfg=_make_fake_config(NEO4J_PASSWORD="changeme"))
        assert any(
            i.severity == "fail" and "NEO4J_PASSWORD" in i.field
            for i in issues
        )

    def test_absent_openai_key_generates_no_issue(self):
        """OPENAI_API_KEY is optional — None means not configured, not an error."""
        issues = validate_config(cfg=_make_fake_config(OPENAI_API_KEY=None))
        openai_issues = [i for i in issues if "OPENAI_API_KEY" in i.field]
        assert openai_issues == []

    def test_absent_lm_studio_key_generates_no_issue(self):
        issues = validate_config(cfg=_make_fake_config(LM_STUDIO_API_KEY=None))
        lm_studio_issues = [i for i in issues if "LM_STUDIO_API_KEY" in i.field]
        assert lm_studio_issues == []

    def test_placeholder_lm_studio_key_is_warn(self):
        issues = validate_config(
            cfg=_make_fake_config(LM_STUDIO_API_KEY="placeholder")
        )
        assert any(
            i.severity == "warn" and "LM_STUDIO_API_KEY" in i.field
            for i in issues
        )

    def test_bad_openai_prefix_is_warn(self):
        issues = validate_config(cfg=_make_fake_config(OPENAI_API_KEY="notsk-badkey"))
        assert any(
            i.severity == "warn" and "OPENAI_API_KEY" in i.field
            for i in issues
        )

    def test_issue_fields_are_strings(self):
        issues = validate_config(cfg=_make_fake_config(ANTHROPIC_API_KEY="your-key-here"))
        for issue in issues:
            assert isinstance(issue.field, str)
            assert isinstance(issue.detail, str)
            assert issue.severity in ("warn", "fail")

    def test_unchecked_model_emits_warn(self):
        from utils.model_registry import get_configured_models

        target = next(pair for pair in get_configured_models())
        registry = _make_registry(known_by_provider=_known_models_except(target))
        issues = _check_configured_models_in_registry(registry=registry)
        assert any(
            i.severity == "warn" and target[1] in i.detail
            for i in issues
        )

    def test_unavailable_model_emits_fail(self):
        from utils.model_registry import get_configured_models

        target = next(pair for pair in get_configured_models())
        registry = _make_registry(
            known_by_provider=_known_models_except(target),
            unavailable_by_provider={target[0]: [target[1]]},
        )
        issues = _check_configured_models_in_registry(registry=registry)
        assert any(
            i.severity == "fail" and target[1] in i.detail
            for i in issues
        )

    def test_empty_registry_emits_warn(self, tmp_path):
        issues = _check_configured_models_in_registry(
            registry_path=tmp_path / "missing_model_registry.json"
        )
        assert any(
            i.severity == "warn" and "not populated" in i.detail
            for i in issues
        )
