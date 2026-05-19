from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from coordinators.base import Coordinator


DREAM_CADENCE_SECONDS = 300
DREAM_LOG_MAXLEN = 100
ASSOCIATION_WINDOW = 5

_TAG_MARKERS = (
    ("idea", ("what if", "maybe", "could", "imagine", "idea", "concept")),
    ("question", ("why", "how", "what", "wonder", "?")),
    ("observation", ("noticed", "seems", "appears", "looks like", "feels like")),
    (
        "feeling",
        (
            "frustrated",
            "excited",
            "tired",
            "anxious",
            "happy",
            "worried",
            "energized",
            "stuck",
            "bored",
        ),
    ),
)


@dataclass
class DreamItem:
    text: str
    tags: list[str]
    timestamp: datetime
    associations: list[int] = field(default_factory=list)


@dataclass
class DreamState:
    log: deque = field(default_factory=lambda: deque(maxlen=DREAM_LOG_MAXLEN))
    idle_decay_cycles: int = 0
    last_intake: datetime | None = None


Clock = Callable[[], datetime]
DecayFn = Callable[[], None]


class Dream(Coordinator):
    name = "dream"

    def __init__(
        self,
        clock: Clock | None = None,
        decay_fn: DecayFn | None = None,
    ) -> None:
        self.clock = clock or (lambda: datetime.now(UTC))
        self.decay_fn = decay_fn
        self.state = DreamState()

    def intake(self, text: str) -> DreamItem:
        now = self.clock()
        item = DreamItem(
            text=text,
            tags=_detect_tags(text),
            timestamp=now,
            associations=[],
        )
        self.state.log.append(item)
        self.state.last_intake = now
        return item

    async def background_tick(self, awareness_queue) -> None:
        self._associate_recent_items()
        if self.decay_fn is not None:
            self.decay_fn()
        self.state.idle_decay_cycles += 1

    def process(self, packet: dict) -> dict:
        packet["dream_log_size"] = len(self.state.log)
        return packet

    def _associate_recent_items(self) -> None:
        if len(self.state.log) < 2:
            return

        log_items = list(self.state.log)
        start = max(0, len(log_items) - ASSOCIATION_WINDOW)
        for left_index in range(start, len(log_items)):
            for right_index in range(left_index + 1, len(log_items)):
                left = log_items[left_index]
                right = log_items[right_index]
                if not set(left.tags).intersection(right.tags):
                    continue
                _append_unique(left.associations, right_index)
                _append_unique(right.associations, left_index)


def _detect_tags(text: str) -> list[str]:
    lower_text = text.lower()
    tags: list[str] = []

    for tag, markers in _TAG_MARKERS:
        if any(marker in lower_text for marker in markers):
            tags.append(tag)

    return tags or ["fragment"]


def _append_unique(values: list[int], value: int) -> None:
    if value not in values:
        values.append(value)
