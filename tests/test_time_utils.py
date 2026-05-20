"""
Unit tests for utils/time_utils.py — no Neo4j required.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta

import pytest

from utils.time_utils import (
    elapsed_seconds,
    format_elapsed,
    is_sleep_window,
    now_iso,
    unix_to_iso,
)


# ---------------------------------------------------------------------------
# now_iso
# ---------------------------------------------------------------------------

def test_now_iso_returns_string():
    result = now_iso()
    assert isinstance(result, str)


def test_now_iso_is_parseable():
    result = now_iso()
    parsed = datetime.fromisoformat(result)
    assert parsed.tzinfo is not None


def test_now_iso_is_recent():
    before = datetime.now(timezone.utc)
    result = now_iso()
    after = datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(result)
    assert before <= parsed <= after


# ---------------------------------------------------------------------------
# elapsed_seconds
# ---------------------------------------------------------------------------

def test_elapsed_seconds_recent_timestamp_is_small():
    ts = now_iso()
    time.sleep(0.05)
    elapsed = elapsed_seconds(ts)
    assert 0.0 <= elapsed < 1.0


def test_elapsed_seconds_past_timestamp():
    past = (datetime.now(timezone.utc) - timedelta(seconds=100)).isoformat()
    elapsed = elapsed_seconds(past)
    assert 99.0 <= elapsed <= 102.0


def test_elapsed_seconds_handles_naive_timestamp():
    """Naive (no timezone) ISO strings are treated as UTC."""
    naive = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    elapsed = elapsed_seconds(naive)
    assert 0.0 <= elapsed < 2.0


def test_elapsed_seconds_never_negative():
    future = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat()
    result = elapsed_seconds(future)
    assert result == 0.0


# ---------------------------------------------------------------------------
# format_elapsed
# ---------------------------------------------------------------------------

def test_format_elapsed_seconds():
    assert format_elapsed(45) == "45s ago"


def test_format_elapsed_minutes():
    assert format_elapsed(130) == "2m ago"


def test_format_elapsed_hours():
    assert format_elapsed(3700) == "1h 1m ago"


def test_format_elapsed_days():
    assert format_elapsed(90061) == "1d 1h ago"


def test_format_elapsed_zero():
    assert format_elapsed(0) == "0s ago"


def test_format_elapsed_negative_clamps_to_zero():
    assert format_elapsed(-10) == "0s ago"


# ---------------------------------------------------------------------------
# unix_to_iso
# ---------------------------------------------------------------------------

def test_unix_to_iso_epoch():
    result = unix_to_iso(0.0)
    assert result.startswith("1970-01-01")


def test_unix_to_iso_is_utc():
    result = unix_to_iso(0.0)
    assert "+00:00" in result or "Z" in result or "UTC" in result or result.endswith("+00:00")


def test_unix_to_iso_roundtrips():
    now = time.time()
    iso = unix_to_iso(now)
    parsed = datetime.fromisoformat(iso)
    assert abs(parsed.timestamp() - now) < 0.001


# ---------------------------------------------------------------------------
# is_sleep_window
# ---------------------------------------------------------------------------

def test_is_sleep_window_always_false_if_empty_range():
    """A zero-width range (start == end) is never active."""
    # Both start==end means no hour satisfies start <= h < start
    result = is_sleep_window(sleep_start_hour=3, sleep_end_hour=3)
    assert result is False


def test_is_sleep_window_midnight_to_six_contains_three():
    """Hour 3 is inside [0, 6)."""
    # We can't control the real clock, so verify the logic function directly.
    from utils import time_utils as tu
    import unittest.mock as mock

    with mock.patch("utils.time_utils.datetime") as mock_dt:
        mock_dt.now.return_value.hour = 3
        result = is_sleep_window(sleep_start_hour=0, sleep_end_hour=6)
    assert result is True


def test_is_sleep_window_midnight_to_six_excludes_ten():
    """Hour 10 is outside [0, 6)."""
    from utils import time_utils as tu
    import unittest.mock as mock

    with mock.patch("utils.time_utils.datetime") as mock_dt:
        mock_dt.now.return_value.hour = 10
        result = is_sleep_window(sleep_start_hour=0, sleep_end_hour=6)
    assert result is False


def test_is_sleep_window_wraps_midnight():
    """Hour 23 is inside [23, 4) — window wraps past midnight."""
    from utils import time_utils as tu
    import unittest.mock as mock

    with mock.patch("utils.time_utils.datetime") as mock_dt:
        mock_dt.now.return_value.hour = 23
        result = is_sleep_window(sleep_start_hour=23, sleep_end_hour=4)
    assert result is True


def test_is_sleep_window_wraps_midnight_early_morning():
    """Hour 2 is inside [23, 4) — window wraps past midnight."""
    from utils import time_utils as tu
    import unittest.mock as mock

    with mock.patch("utils.time_utils.datetime") as mock_dt:
        mock_dt.now.return_value.hour = 2
        result = is_sleep_window(sleep_start_hour=23, sleep_end_hour=4)
    assert result is True
