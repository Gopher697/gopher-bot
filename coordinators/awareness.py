from __future__ import annotations

from coordinators.base import Coordinator
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
    ):
        self.sensory = sensory or Sensory()
        self.memory = memory or Memory()
        self.reason = reason or Reason(
            memory=self.memory if isinstance(self.memory, Memory) else None
        )
        self.voice = voice or Voice()

    def run(self, message: str, **packet_overrides) -> dict:
        packet = {"message": message, "input_type": "text"}
        packet.update(packet_overrides)
        self.assess_tier(packet)
        for coordinator in (self.sensory, self.memory, self.reason):
            packet = coordinator.process(packet)
            if "error" in packet:
                break
        return self.voice.process(packet)

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
