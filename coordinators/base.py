from __future__ import annotations

from abc import ABC, abstractmethod
import json
from pathlib import Path
from typing import Any

from coordinators.bid import BidQueue


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COORDINATOR_LOG_PATH = PROJECT_ROOT / "logs" / "coordinator_ticks.jsonl"


class Coordinator(ABC):
    name: str

    @abstractmethod
    def process(self, packet: dict) -> dict:
        """Read from packet, add coordinator output, and return the packet."""

    async def background_tick(self, bid_queue: BidQueue) -> None:
        """Run optional background work and submit bids when useful."""
        return None


def build_coordinator_log_entry(
    coordinator_name: str,
    timestamp: float,
    *,
    event: str | None = None,
    confidence: float = 0.0,
    accepted: bool | None = None,
    outcome_quality: float | None = None,
    tier_used: str | None = None,
    actual_cost_usd: float = 0.0,
    reasoning_trace: str | None = None,
    error: str | None = None,
    submitted_bid_count: int = 0,
) -> dict[str, Any]:
    return {
        "coordinator_name": str(coordinator_name),
        "timestamp": float(timestamp),
        "event": str(event or "tick"),
        "confidence": _clamp_unit(_safe_float(confidence, 0.0)),
        "accepted": accepted,
        "outcome_quality": outcome_quality,
        "tier_used": tier_used,
        "actual_cost_usd": max(0.0, _safe_float(actual_cost_usd, 0.0)),
        "reasoning_trace": reasoning_trace,
        "error": error,
        "submitted_bid_count": max(0, int(submitted_bid_count)),
    }


def append_coordinator_log_entry(
    entry: dict[str, Any],
    path: Path = COORDINATOR_LOG_PATH,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def read_coordinator_log_entries(
    limit: int = 50,
    path: Path = COORDINATOR_LOG_PATH,
) -> list[dict[str, Any]]:
    limit = int(limit)
    if limit <= 0:
        return []

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    entries: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            entries.append(item)
    return entries


def backfill_coordinator_log_acceptance(
    coordinator_name: str,
    bid_timestamp: float,
    accepted: bool,
    path: Path = COORDINATOR_LOG_PATH,
) -> bool:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False

    parsed: list[dict[str, Any] | None] = []
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            parsed.append(None)
            continue
        parsed.append(item if isinstance(item, dict) else None)

    target_index = _find_acceptance_backfill_index(
        parsed,
        coordinator_name,
        float(bid_timestamp),
    )
    if target_index is None:
        return False

    parsed[target_index]["accepted"] = bool(accepted)  # type: ignore[index]
    rewritten = []
    for original, item in zip(lines, parsed, strict=False):
        if item is None:
            rewritten.append(original)
        else:
            rewritten.append(json.dumps(item, sort_keys=True))
    path.write_text("\n".join(rewritten) + ("\n" if rewritten else ""), encoding="utf-8")
    return True


def _find_acceptance_backfill_index(
    entries: list[dict[str, Any] | None],
    coordinator_name: str,
    bid_timestamp: float,
) -> int | None:
    candidates: list[tuple[float, int]] = []
    for index, entry in enumerate(entries):
        if not entry:
            continue
        if entry.get("coordinator_name") != coordinator_name:
            continue
        if entry.get("accepted") is not None:
            continue
        try:
            timestamp = float(entry.get("timestamp"))
        except (TypeError, ValueError):
            timestamp = bid_timestamp
        candidates.append((abs(timestamp - bid_timestamp), index))

    if not candidates:
        return None
    return min(candidates, key=lambda item: item[0])[1]


def _clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
