from __future__ import annotations

from dataclasses import asdict
import time
from collections.abc import Callable

from coordinators.base import Coordinator
from coordinators.bid import Bid, BidQueue
from coordinators.memory import Memory
from coordinators.reason import Reason
from coordinators.sensory import Sensory
from coordinators.tier_config import DEFAULT_TIER
from coordinators.voice import Voice


class Awareness:
    def __init__(
        self,
        sensory: Coordinator | None = None,
        memory: Memory | Coordinator | None = None,
        reason: Coordinator | None = None,
        voice: Voice | Coordinator | None = None,
        bid_queue: BidQueue | None = None,
        time_fn: Callable[[], float] = time.time,
    ):
        self.sensory = sensory or Sensory()
        self.memory = memory or Memory()
        self.reason = reason or Reason(
            memory=self.memory if isinstance(self.memory, Memory) else None
        )
        self.voice = voice or Voice()
        self.bid_queue = bid_queue or BidQueue()
        self.active_task_in_progress = False
        self.last_active = 0.0
        self._time_fn = time_fn
        self._activity_callbacks: list[Callable[[float], None]] = []

    def synchronous_run(self, message: str, **packet_overrides) -> dict:
        self._mark_active()
        self.active_task_in_progress = True
        packet = {"message": message, "input_type": "text"}
        packet.update(packet_overrides)
        try:
            self.assess_tier(packet)

            packet = self.sensory.process(packet)
            if "error" in packet:
                return self.voice.process(packet)

            packet = self.memory.process(packet)
            if "error" in packet:
                return self.voice.process(packet)

            self._drain_bids_into_packet(packet)

            packet = self.reason.process(packet)
            return self.voice.process(packet)
        finally:
            self.active_task_in_progress = False
            self._mark_active()

    def run(self, message: str, **packet_overrides) -> dict:
        return self.synchronous_run(message, **packet_overrides)

    async def gate_bids(self) -> list[Bid]:
        if self.active_task_in_progress or self.bid_queue.empty():
            return []
        return self.bid_queue.get_pending()

    def assess_tier(self, packet: dict) -> dict:
        if "tier" in packet:
            return packet

        if packet.get("high_stakes") is True:
            packet["tier"] = 3
            return packet

        message = str(packet.get("message", ""))
        if len(message) < 100 and "?" not in message:
            packet["tier"] = 1
            return packet

        packet["tier"] = DEFAULT_TIER
        return packet

    def add_activity_callback(self, callback: Callable[[float], None]) -> None:
        if callback not in self._activity_callbacks:
            self._activity_callbacks.append(callback)

    def _mark_active(self) -> None:
        self.last_active = self._time_fn()
        for callback in list(self._activity_callbacks):
            callback(self.last_active)

    def _drain_bids_into_packet(self, packet: dict) -> None:
        bids = self.bid_queue.get_pending()
        packet["background_bids"] = [asdict(bid) for bid in bids]
        bid_context = _format_bid_context(bids)
        packet["bid_context"] = bid_context

        if not bid_context:
            return

        memory_context = str(packet.get("memory_context") or "").strip()
        if memory_context:
            packet["memory_context"] = f"{memory_context}\n\n{bid_context}"
        else:
            packet["memory_context"] = bid_context


def _format_bid_context(bids: list[Bid]) -> str:
    if not bids:
        return ""

    lines = ["Background coordinator bids:"]
    for bid in bids:
        content = str(bid.content).strip()
        if not content:
            continue
        lines.append(
            f"- {bid.coordinator_name} (priority {bid.priority}): {content}"
        )
    return "\n".join(lines).strip()
