from __future__ import annotations

import asyncio
import itertools
import threading
from dataclasses import dataclass


PRIORITY_SAFETY = 1
PRIORITY_HANDS = 2
PRIORITY_MIRROR = 3
PRIORITY_CURIOSITY = 4
PRIORITY_PATTERN = 5
PRIORITY_DRIVE = 6
PRIORITY_DEFAULT = 7


@dataclass(frozen=True)
class Bid:
    coordinator_name: str
    content: str
    priority: int
    timestamp: float


class BidQueue:
    def __init__(self):
        self._queue: asyncio.PriorityQueue[tuple[int, float, int, Bid]] = (
            asyncio.PriorityQueue()
        )
        self._counter = itertools.count()
        self._lock = threading.RLock()

    def submit(self, bid: Bid) -> None:
        with self._lock:
            self._queue.put_nowait(
                (int(bid.priority), float(bid.timestamp), next(self._counter), bid)
            )

    def get_pending(self) -> list[Bid]:
        bids: list[Bid] = []
        with self._lock:
            while not self._queue.empty():
                try:
                    _, _, _, bid = self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                bids.append(bid)
                self._queue.task_done()
        return bids

    def clear(self) -> None:
        self.get_pending()

    def qsize(self) -> int:
        with self._lock:
            return self._queue.qsize()

    def empty(self) -> bool:
        return self.qsize() == 0
