from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from coordinators.base import Coordinator


TRUST_LEVEL_REACTIVE = 0
TRUST_LEVEL_SUPERVISED = 1
TRUST_LEVEL_EXTENDED = 2
TRUST_LEVEL_AUTONOMOUS = 3

KEEPER_CADENCE_SECONDS = 300
KEEPER_PRIORITY = 4

MIN_CLEAN_NREM_STREAK = 3

DREAM_LOG_DIR = "logs/dream"
DREAM_LOG_SCAN_LIMIT = 10


@dataclass
class KeeperState:
    trust_level: int = TRUST_LEVEL_REACTIVE
    clean_nrem_streak: int = 0
    last_demotion_reason: str = ""
    last_elevation_ts: float = 0.0
    last_demoted_ts: float = 0.0
    last_bid_content: str | None = None


@dataclass(frozen=True)
class KeeperBid:
    coordinator_name: str
    content: str
    priority: int
    timestamp: float
    source: str = "keeper"
    type: str = "trust_level_signal"


class Keeper(Coordinator):
    name = "keeper"

    def __init__(
        self,
        dream_log_reader: Callable[[], list[dict]] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        import time as _time

        self.dream_log_reader = dream_log_reader or _default_dream_log_reader
        self.clock = clock or _time.time
        self.state = KeeperState()

    def process(self, packet: dict) -> dict:
        alerts = _alert_items(packet.get("defender_alerts", []))
        if alerts and self.state.trust_level > TRUST_LEVEL_REACTIVE:
            self.state.trust_level = TRUST_LEVEL_REACTIVE
            self.state.clean_nrem_streak = 0
            self.state.last_demotion_reason = (
                f"inner defender alert: {alerts[0][:80]}"
            )
            self.state.last_demoted_ts = self.clock()

        if not alerts and self.state.trust_level == TRUST_LEVEL_REACTIVE:
            if self.state.clean_nrem_streak >= MIN_CLEAN_NREM_STREAK:
                self.state.trust_level = TRUST_LEVEL_SUPERVISED
                self.state.last_elevation_ts = self.clock()

        packet["trust_level"] = self.state.trust_level
        packet["keeper_context"] = _build_keeper_context(self.state)

        keeper_ctx = str(packet.get("keeper_context") or "").strip()
        if keeper_ctx:
            existing = str(packet.get("memory_context") or "").strip()
            packet["memory_context"] = (
                f"{existing}\n\n{keeper_ctx}" if existing else keeper_ctx
            )

        return packet

    async def background_tick(self, awareness_queue) -> None:
        entries = self.dream_log_reader()
        self.state.clean_nrem_streak = _compute_clean_streak(entries)

        observation = _build_observation(self.state)
        if not observation or observation == self.state.last_bid_content:
            return

        import time as _time

        bid = KeeperBid(
            coordinator_name=self.name,
            content=observation,
            priority=KEEPER_PRIORITY,
            timestamp=_time.time(),
        )
        try:
            awareness_queue.submit(bid)
            self.state.last_bid_content = observation
        except Exception:
            pass


def _default_dream_log_reader() -> list[dict]:
    import json
    import pathlib

    log_dir = pathlib.Path(DREAM_LOG_DIR)
    if not log_dir.exists():
        return []
    try:
        files = sorted(log_dir.glob("*.json"))[-DREAM_LOG_SCAN_LIMIT:]
        entries = []
        for path in files:
            try:
                entries.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        return entries
    except Exception:
        return []


def _compute_clean_streak(entries: list[dict]) -> int:
    streak = 0
    for entry in reversed(entries):
        audit = entry.get("audit", {})
        if audit.get("chain_ok", True) is True:
            streak += 1
        else:
            break
    return streak


def _build_keeper_context(state: KeeperState) -> str:
    reason = state.last_demotion_reason or "none"
    return (
        f"trust_level={state.trust_level} "
        f"clean_nrem_streak={state.clean_nrem_streak} "
        f"last_demotion={reason}"
    )


def _build_observation(state: KeeperState) -> str | None:
    level_name = {
        TRUST_LEVEL_REACTIVE: "reactive",
        TRUST_LEVEL_SUPERVISED: "supervised",
    }.get(state.trust_level, str(state.trust_level))

    if state.trust_level == TRUST_LEVEL_REACTIVE and state.last_demotion_reason:
        return (
            f"Trust level: {level_name} (streak={state.clean_nrem_streak}) "
            f"-- demoted: {state.last_demotion_reason}"
        )
    if state.trust_level >= TRUST_LEVEL_SUPERVISED:
        return (
            f"Trust level: {level_name} (streak={state.clean_nrem_streak}) "
            "-- local autonomous writes permitted"
        )
    return f"Trust level: {level_name} (streak={state.clean_nrem_streak})"


def _alert_items(defender_alerts: Any) -> list[str]:
    if isinstance(defender_alerts, str):
        alert = defender_alerts.strip()
        return [alert] if alert else []
    if isinstance(defender_alerts, (list, tuple)):
        return [str(item).strip() for item in defender_alerts if str(item).strip()]
    return []
