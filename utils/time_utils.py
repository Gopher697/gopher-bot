"""
utils/time_utils.py

Shared time utilities for Gopher-bot coordinators.

All timestamps are UTC ISO-8601 strings. Unix timestamps (float) are used
only for internal elapsed-time arithmetic and are never stored in the graph.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def elapsed_seconds(iso_timestamp: str) -> float:
    """
    Return the number of seconds elapsed since the given ISO-8601 timestamp.

    Handles both timezone-aware and naive (assumed UTC) timestamps.

    Args:
        iso_timestamp: An ISO-8601 datetime string (e.g. from now_iso()).

    Returns:
        Elapsed time in seconds (>= 0.0).
    """
    then = datetime.fromisoformat(iso_timestamp)
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    delta = (now - then).total_seconds()
    return max(0.0, delta)


def format_elapsed(seconds: float) -> str:
    """
    Return a compact human-readable description of an elapsed duration.

    Examples:
        45      → "45s ago"
        130     → "2m ago"
        3700    → "1h 1m ago"
        90000   → "1d 1h ago"

    Args:
        seconds: Elapsed duration in seconds (>= 0).

    Returns:
        Human-readable string.
    """
    seconds = max(0.0, float(seconds))
    if seconds < 60:
        return f"{int(seconds)}s ago"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    elif seconds < 86400:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        return f"{h}h {m}m ago"
    else:
        d = int(seconds // 86400)
        h = int((seconds % 86400) // 3600)
        return f"{d}d {h}h ago"


def unix_to_iso(unix_timestamp: float) -> str:
    """
    Convert a Unix timestamp (float seconds since epoch) to ISO-8601 UTC string.

    Args:
        unix_timestamp: Seconds since Unix epoch.

    Returns:
        ISO-8601 UTC datetime string.
    """
    return datetime.fromtimestamp(unix_timestamp, tz=timezone.utc).isoformat()


def is_sleep_window(
    sleep_start_hour: int = 0,
    sleep_end_hour: int = 6,
) -> bool:
    """
    Return True if the current LOCAL hour falls within the sleep window.

    Used by Dream to decide whether NREM consolidation is appropriate
    (run during Gopher's sleep, not during active hours).

    The window [sleep_start_hour, sleep_end_hour) is half-open. Wrapping
    past midnight is supported (e.g. sleep_start_hour=23, sleep_end_hour=6).

    Args:
        sleep_start_hour: First hour of sleep window (0–23). Default 0.
        sleep_end_hour:   First hour after sleep window (0–23). Default 6.

    Returns:
        True if local time is within the sleep window.
    """
    hour = datetime.now().hour      # local time intentional for sleep schedule
    if sleep_start_hour <= sleep_end_hour:
        return sleep_start_hour <= hour < sleep_end_hour
    else:                           # window wraps midnight
        return hour >= sleep_start_hour or hour < sleep_end_hour
