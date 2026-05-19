from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping
from typing import Any

from coordinators.base import Coordinator
from coordinators.bid import BidQueue


BACKGROUND_INTERVALS = {
    "feeling": 30.0,
    "pattern_monitor": 120.0,
    "curiosity": 180.0,
    "drive": 3600.0,
}
DREAM_IDLE_SECONDS = 300.0
BACKGROUND_COORDINATORS = (
    "feeling",
    "pattern_monitor",
    "curiosity",
    "drive",
    "dream",
)


class _NoopBackgroundCoordinator(Coordinator):
    def __init__(self, name: str):
        self.name = name

    def process(self, packet: dict) -> dict:
        return packet


class BrainLoop:
    def __init__(
        self,
        coordinators: Mapping[str, Coordinator] | None = None,
        intervals: Mapping[str, float] | None = None,
        time_fn: Callable[[], float] = time.time,
        sleep_interval: float = 1.0,
        idle_threshold: float = DREAM_IDLE_SECONDS,
    ):
        self.coordinators = dict(coordinators or _default_background_coordinators())
        self.intervals = dict(BACKGROUND_INTERVALS)
        if intervals:
            self.intervals.update(intervals)
        self.time_fn = time_fn
        self.sleep_interval = sleep_interval
        self.idle_threshold = idle_threshold
        self.last_ticks: dict[str, float] = {}
        self.last_active = self.time_fn()
        self.last_errors: dict[str, str] = {}
        self.awareness: Any | None = None
        self.bid_queue: BidQueue | None = None
        self.running = False
        self._stop_requested = False

    def bind_awareness(self, awareness: Any) -> None:
        self.awareness = awareness
        self.bid_queue = awareness.bid_queue
        awareness_last_active = float(getattr(awareness, "last_active", 0.0) or 0.0)
        if awareness_last_active:
            self.last_active = awareness_last_active
        add_callback = getattr(awareness, "add_activity_callback", None)
        if callable(add_callback):
            add_callback(self.mark_active)

    def mark_active(self, timestamp: float | None = None) -> None:
        self.last_active = float(timestamp if timestamp is not None else self.time_fn())

    def stop(self) -> None:
        self._stop_requested = True

    async def start(self, awareness: Any) -> None:
        self.bind_awareness(awareness)
        await self.run()

    async def run(self) -> None:
        if self.bid_queue is None:
            raise RuntimeError("BrainLoop must be bound to Awareness before run()")

        self.running = True
        self._stop_requested = False
        try:
            while not self._stop_requested:
                await self.tick_once()
                await asyncio.sleep(self.sleep_interval)
        except KeyboardInterrupt:
            self.stop()
        finally:
            self.running = False

    async def tick_once(self) -> None:
        if self.bid_queue is None:
            raise RuntimeError("BrainLoop must be bound to Awareness before ticking")

        self._sync_last_active_from_awareness()
        now = self.time_fn()
        for name, coordinator in self.coordinators.items():
            if not self._should_tick(name, now):
                continue
            await self._tick_coordinator(name, coordinator)
            self.last_ticks[name] = now

    def _sync_last_active_from_awareness(self) -> None:
        if self.awareness is None:
            return
        awareness_last_active = float(getattr(self.awareness, "last_active", 0.0) or 0.0)
        if awareness_last_active > self.last_active:
            self.last_active = awareness_last_active

    def _should_tick(self, name: str, now: float) -> bool:
        if name == "dream":
            return self._should_tick_dream(now)

        interval = self.intervals.get(name)
        if interval is None:
            return False

        last_tick = self.last_ticks.get(name)
        return last_tick is None or now - last_tick >= interval

    def _should_tick_dream(self, now: float) -> bool:
        if now - self.last_active < self.idle_threshold:
            return False

        last_tick = self.last_ticks.get("dream")
        return last_tick is None or now - last_tick >= self.idle_threshold

    async def _tick_coordinator(self, name: str, coordinator: Coordinator) -> None:
        try:
            await coordinator.background_tick(self.bid_queue)
            self.last_errors.pop(name, None)
        except Exception as exc:
            self.last_errors[name] = str(exc)


def _default_background_coordinators() -> dict[str, Coordinator]:
    return {
        name: _NoopBackgroundCoordinator(name)
        for name in BACKGROUND_COORDINATORS
    }
