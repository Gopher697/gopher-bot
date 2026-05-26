"""Tests for local timezone display in Orientation operational context."""
from __future__ import annotations

import time
from unittest.mock import patch

from coordinators.orientation import _operational_context


def test_operational_context_utc_fallback_shows_local_utc():
    with patch("coordinators.orientation._USER_TIMEZONE", "UTC"):
        result = _operational_context(
            {"current_time": "2026-05-26T01:00:00Z"},
            time.time(),
        )

    assert "Current time (UTC): 2026-05-26T01:00:00Z" in result
    assert "Local time:" in result
    assert "UTC" in result


def test_operational_context_valid_timezone_shows_eastern_abbreviation():
    with patch("coordinators.orientation._USER_TIMEZONE", "America/New_York"):
        result = _operational_context(
            {"current_time": "2026-05-26T01:00:00Z"},
            time.time(),
        )

    assert "Current time (UTC): 2026-05-26T01:00:00Z" in result
    assert "Local time:" in result
    assert "EDT" in result or "EST" in result


def test_operational_context_invalid_timezone_degrades_to_utc_only():
    with patch("coordinators.orientation._USER_TIMEZONE", "Invalid/Zone"):
        result = _operational_context(
            {"current_time": "2026-05-26T01:00:00Z"},
            time.time(),
        )

    assert "Current time (UTC): 2026-05-26T01:00:00Z" in result
    assert "Local time:" not in result


def test_operational_context_missing_current_time_has_no_time_lines():
    result = _operational_context({}, time.time())

    assert "Current time (UTC):" not in result
    assert "Local time:" not in result


def test_operational_context_dst_summer_is_edt():
    with patch("coordinators.orientation._USER_TIMEZONE", "America/New_York"):
        result = _operational_context(
            {"current_time": "2026-07-01T18:00:00Z"},
            time.time(),
        )

    assert "Local time: Wed 2026-07-01 14:00 EDT" in result


def test_operational_context_dst_winter_is_est():
    with patch("coordinators.orientation._USER_TIMEZONE", "America/New_York"):
        result = _operational_context(
            {"current_time": "2026-01-01T18:00:00Z"},
            time.time(),
        )

    assert "Local time: Thu 2026-01-01 13:00 EST" in result
