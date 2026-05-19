from __future__ import annotations

from abc import ABC, abstractmethod


class Coordinator(ABC):
    name: str

    @abstractmethod
    def process(self, packet: dict) -> dict:
        """Read from packet, add coordinator output, and return the packet."""
