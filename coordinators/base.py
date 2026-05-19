from __future__ import annotations

from abc import ABC, abstractmethod

from coordinators.bid import BidQueue


class Coordinator(ABC):
    name: str

    @abstractmethod
    def process(self, packet: dict) -> dict:
        """Read from packet, add coordinator output, and return the packet."""

    async def background_tick(self, bid_queue: BidQueue) -> None:
        """Run optional background work and submit bids when useful."""
        return None
