"""
Tests for cognition fixes:
  - _parse_reminder_trigger absolute time parsing
  - _format_observation source_type tagging
  - VALID_SOURCE_TYPES includes "perceived"
  - Reason system prompt contains orientation authority language
"""
from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# _parse_reminder_trigger - absolute time
# ---------------------------------------------------------------------------

def test_parse_reminder_absolute_am_with_colon(monkeypatch):
    """'at 9:00 am' before 9am -> trigger is same day at 9am."""
    from coordinators.awareness import _parse_reminder_trigger
    from world_models import config

    monkeypatch.setattr(config, "USER_TIMEZONE", "UTC", raising=False)

    # now = 2026-05-26 08:00:00 UTC
    now = dt.datetime(2026, 5, 26, 8, 0, 0, tzinfo=dt.timezone.utc).timestamp()
    result = _parse_reminder_trigger("remind me at 9:00 am", now)

    assert result is not None
    assert result > now
    assert result < now + 3 * 3600


def test_parse_reminder_absolute_pm_no_colon(monkeypatch):
    """'at 9 pm' should resolve to a time later today."""
    from coordinators.awareness import _parse_reminder_trigger
    from world_models import config

    monkeypatch.setattr(config, "USER_TIMEZONE", "UTC", raising=False)

    # now = 08:00 UTC
    now = dt.datetime(2026, 5, 26, 8, 0, 0, tzinfo=dt.timezone.utc).timestamp()
    result = _parse_reminder_trigger("set a reminder at 9 pm", now)

    assert result is not None
    assert result > now
    assert result < now + 86400


def test_parse_reminder_absolute_rolls_to_next_day(monkeypatch):
    """'at 7 am' when it's already 10am -> next day."""
    from coordinators.awareness import _parse_reminder_trigger
    from world_models import config

    monkeypatch.setattr(config, "USER_TIMEZONE", "UTC", raising=False)

    # now = 10:00 UTC
    now = dt.datetime(2026, 5, 26, 10, 0, 0, tzinfo=dt.timezone.utc).timestamp()
    result = _parse_reminder_trigger("at 7 am please", now)

    assert result is not None
    assert result > now
    assert result <= now + 86400


def test_parse_reminder_absolute_returns_none_for_no_time():
    """'remind me about the meeting' has no time phrase -> None."""
    from coordinators.awareness import _parse_reminder_trigger

    result = _parse_reminder_trigger("remind me about the meeting", 1_000_000.0)
    assert result is None


def test_parse_reminder_relative_still_works():
    """Relative parsing must not be broken by the absolute time addition."""
    from coordinators.awareness import _parse_reminder_trigger

    now = 1_000_000.0
    result = _parse_reminder_trigger("in 30 minutes", now)
    assert result == now + 30 * 60


# ---------------------------------------------------------------------------
# _format_observation - source_type tagging
# ---------------------------------------------------------------------------

def test_format_observation_no_tag_for_observed():
    """Default 'observed' source_type produces no source: tag."""
    from coordinators.memory import _format_observation

    obs = {"content": "User said hello", "source_type": "observed", "confidence": 0.9}
    result = _format_observation(obs, None)
    assert "source:" not in result
    assert "User said hello" in result


def test_format_observation_tags_inferred():
    """Inferred observations get a source:inferred tag."""
    from coordinators.memory import _format_observation

    obs = {
        "content": "User appears to prefer dark mode",
        "source_type": "inferred",
        "confidence": 0.6,
    }
    result = _format_observation(obs, None)
    assert "source:inferred" in result


def test_format_observation_tags_external_content():
    """External content gets a source:external_content tag."""
    from coordinators.memory import _format_observation

    obs = {
        "content": "[report.pdf chunk 1]\nQ1 revenue was $3.2M",
        "source_type": "external_content",
    }
    result = _format_observation(obs, None)
    assert "source:external_content" in result


def test_format_observation_tags_perceived():
    """Perceived source type from VisionSensor snapshots is tagged."""
    from coordinators.memory import _format_observation

    obs = {"content": "Window: Chrome - Google Maps tab open", "source_type": "perceived"}
    result = _format_observation(obs, None)
    assert "source:perceived" in result


# ---------------------------------------------------------------------------
# VALID_SOURCE_TYPES includes "perceived"
# ---------------------------------------------------------------------------

def test_perceived_in_valid_source_types():
    """'perceived' must be valid or visual observations fail to persist."""
    from world_models.graph import VALID_SOURCE_TYPES

    assert "perceived" in VALID_SOURCE_TYPES


# ---------------------------------------------------------------------------
# Reason system prompt source authority language
# ---------------------------------------------------------------------------

def test_reason_system_prompt_orientation_authority(monkeypatch):
    """Reason's system prompt says ORIENTATION data is authoritative."""
    from coordinators.memory import Memory
    from coordinators.reason import Reason

    captured: list[str] = []

    def fake_local(message, system_prompt, tier_config, **kwargs):
        captured.append(system_prompt)
        resp = MagicMock()
        resp.choices = [MagicMock()]
        resp.choices[0].message.content = "ok"
        return resp

    monkeypatch.setattr("coordinators.reason._call_local_reasoner", fake_local)
    monkeypatch.setattr(
        "coordinators.reason.get_tier_config",
        lambda tier: {
            "base_url": "http://localhost:1234",
            "reason_model": "test-model",
        },
    )

    reason = Reason(memory=Memory())
    reason.generate_response("what time is it?", "some memory context", tier=1)

    assert captured, "generate_response did not reach _call_local_reasoner"
    prompt = captured[0]
    assert "ORIENTATION" in prompt
    assert "authoritative" in prompt.lower() or "wins" in prompt.lower()
