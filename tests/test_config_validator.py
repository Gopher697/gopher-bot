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

    def test_absent_openai_key_generates_no_issue(self):
        """OPENAI_API_KEY is optional — None means not configured, not an error."""
        issues = validate_config(cfg=_make_fake_config(OPENAI_API_KEY=None))
        openai_issues = [i for i in issues if "OPENAI_API_KEY" in i.field]
        assert openai_issues == []

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
