from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Callable, Mapping
from typing import Any

from coordinators.base import (
    Coordinator,
    append_coordinator_log_entry,
    build_coordinator_log_entry,
)
from coordinators.bid import PRIORITY_PATTERN, BidQueue
from coordinators.mirror_chad import INCUBATION_MAXLEN


BACKGROUND_INTERVALS = {
    "feeling": 30.0,
    "neuromodulation": 30.0,
    "mirror_chad": 60.0,
    "mirror_self": 120.0,
    "pattern_monitor": 90.0,
    "curiosity": 180.0,
    "dream": 300.0,
    "drive": 86400.0,
}
DREAM_IDLE_SECONDS = 300.0
PROACTIVE_VOICE_RATE_LIMIT_SECONDS = 60.0
BACKGROUND_COORDINATORS = (
    "feeling",
    "neuromodulation",
    "mirror_chad",
    "mirror_self",
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
    proactive_voice_enabled = True

    def __init__(
        self,
        coordinators: Mapping[str, Coordinator] | None = None,
        intervals: Mapping[str, float] | None = None,
        time_fn: Callable[[], float] = time.time,
        sleep_interval: float = 1.0,
        idle_threshold: float = DREAM_IDLE_SECONDS,
        mirror_chad_queue: Any | None = None,
        coordinator_log_writer: Callable[[dict[str, Any]], None] | None = None,
        audit_event_emitter: Callable[[dict[str, Any]], None] | None = None,
        proactive_response_emitter: Callable[[str], None] | None = None,
        proactive_voice_enabled: bool | None = None,
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
        self._mirror_chad_queue_was_provided = mirror_chad_queue is not None
        self.mirror_chad_queue = mirror_chad_queue or asyncio.Queue(
            maxsize=INCUBATION_MAXLEN
        )
        self.coordinator_log_writer = (
            coordinator_log_writer or append_coordinator_log_entry
        )
        self.audit_event_emitter = audit_event_emitter
        self.proactive_response_emitter = proactive_response_emitter
        if proactive_voice_enabled is not None:
            self.proactive_voice_enabled = bool(proactive_voice_enabled)
        self.last_proactive_voice_at: float | None = None
        self.running = False
        self._stop_requested = False

    def bind_awareness(self, awareness: Any) -> None:
        self.awareness = awareness
        self.bid_queue = awareness.bid_queue
        if not self._mirror_chad_queue_was_provided:
            awareness_mirror_queue = getattr(awareness, "mirror_chad_queue", None)
            if awareness_mirror_queue is not None:
                self.mirror_chad_queue = awareness_mirror_queue
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
            await self._surface_proactive_voice()

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
        if self.bid_queue is None:
            raise RuntimeError("BrainLoop must be bound to Awareness before ticking")

        submitted_before = self.bid_queue.qsize()
        error: str | None = None
        try:
            if _accepts_mirror_queue(coordinator):
                await coordinator.background_tick(self.bid_queue, self.mirror_chad_queue)
            else:
                await coordinator.background_tick(self.bid_queue)
            self.last_errors.pop(name, None)
        except Exception as exc:
            error = str(exc)
            self.last_errors[name] = error
        finally:
            submitted_after = self.bid_queue.qsize()
            entry = build_coordinator_log_entry(
                name,
                self.time_fn(),
                event=getattr(coordinator, "last_event", None)
                or ("error" if error else "tick"),
                confidence=getattr(coordinator, "last_confidence", 0.0),
                tier_used=getattr(coordinator, "last_tier_used", None),
                actual_cost_usd=getattr(
                    coordinator,
                    "last_actual_cost_usd",
                    0.0,
                ),
                reasoning_trace=getattr(
                    coordinator,
                    "last_reasoning_trace",
                    None,
                ),
                error=error,
                submitted_bid_count=max(0, submitted_after - submitted_before),
            )
            self._write_coordinator_log(entry)
            self._emit_audit_update(entry)

    def _write_coordinator_log(self, entry: dict[str, Any]) -> None:
        try:
            self.coordinator_log_writer(entry)
        except Exception:
            return

    def _emit_audit_update(self, entry: dict[str, Any]) -> None:
        if self.audit_event_emitter is None:
            return

        try:
            self.audit_event_emitter(_audit_update_payload(entry))
        except Exception:
            return

    async def _surface_proactive_voice(self) -> None:
        if not self.proactive_voice_enabled:
            return
        if self.awareness is None or self.proactive_response_emitter is None:
            return
        if bool(getattr(self.awareness, "active_task_in_progress", False)):
            return

        now = self.time_fn()
        if (
            self.last_proactive_voice_at is not None
            and now - self.last_proactive_voice_at < PROACTIVE_VOICE_RATE_LIMIT_SECONDS
        ):
            return

        gate_bids = getattr(self.awareness, "gate_bids", None)
        if not callable(gate_bids):
            return

        try:
            gated = gate_bids()
            bids = await gated if inspect.isawaitable(gated) else gated
        except Exception:
            return

        for bid in list(bids or []):
            if not _is_proactive_priority(bid):
                continue
            response = self._voice_response_for_bid(bid)
            if not response:
                continue
            try:
                self.proactive_response_emitter(response)
            except Exception:
                return
            self.last_proactive_voice_at = now
            return

    def _voice_response_for_bid(self, bid: Any) -> str:
        voice = getattr(self.awareness, "voice", None)
        process = getattr(voice, "process", None)
        content = str(getattr(bid, "content", "") or "").strip()
        if not content:
            return ""
        if not callable(process):
            return content

        packet = {
            "reason_output": content,
            "input_type": "background_bid",
            "proactive": True,
            "source_bid": {
                "coordinator_name": getattr(bid, "coordinator_name", None),
                "priority": getattr(bid, "priority", None),
                "timestamp": getattr(bid, "timestamp", None),
            },
        }
        try:
            packet = process(packet)
        except Exception:
            return content
        return str(packet.get("final_response") or packet.get("reason_output") or "").strip()


def _default_background_coordinators() -> dict[str, Coordinator]:
    from coordinators.curiosity import Curiosity
    from coordinators.dream import Dream
    from coordinators.drive import Drive
    from coordinators.feeling import Feeling
    from coordinators.mirror_chad import MirrorChad
    from coordinators.mirror_self import MirrorSelf
    from coordinators.neuromodulation import Neuromodulation
    from coordinators.pattern_monitor import PatternMonitor

    return {
        "feeling": Feeling(),
        "neuromodulation": Neuromodulation(),
        "mirror_chad": MirrorChad(),
        "mirror_self": MirrorSelf(),
        "pattern_monitor": PatternMonitor(),
        "curiosity": Curiosity(),
        "dream": Dream(),
        "drive": Drive(),
        **{
            name: _NoopBackgroundCoordinator(name)
            for name in BACKGROUND_COORDINATORS
            if name
            not in {
                "feeling",
                "neuromodulation",
                "mirror_chad",
                "mirror_self",
                "pattern_monitor",
                "curiosity",
                "dream",
                "drive",
            }
        },
    }


def _accepts_mirror_queue(coordinator: Coordinator) -> bool:
    return len(inspect.signature(coordinator.background_tick).parameters) >= 2


def _is_proactive_priority(bid: Any) -> bool:
    try:
        return int(getattr(bid, "priority")) <= PRIORITY_PATTERN
    except (TypeError, ValueError):
        return False


def _audit_update_payload(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": entry.get("timestamp"),
        "coordinator": entry.get("coordinator_name"),
        "event": entry.get("event"),
        "confidence": entry.get("confidence"),
        "tier_used": entry.get("tier_used"),
        "actual_cost_usd": entry.get("actual_cost_usd"),
        "accepted": entry.get("accepted"),
    }
