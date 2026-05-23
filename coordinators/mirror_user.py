from __future__ import annotations

import asyncio
import queue
import re
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from coordinators.base import Coordinator


MIRROR_USER_PRIORITY = 2
MIRROR_USER_CADENCE_SECONDS = 60
INCUBATION_MAXLEN = 20

AFFECT_NEUTRAL = "neutral"
AFFECT_FOCUSED = "focused"
AFFECT_CURIOUS = "curious"
AFFECT_FRUSTRATED = "frustrated"
AFFECT_OVERLOADED = "overloaded"
AFFECT_DRIFTING = "drifting"

_FRUSTRATION_MARKERS = (
    "ugh",
    "this isn't working",
    "still not",
    "keeps",
    "again",
    "why won't",
    "broken",
    "wrong",
    "fix this",
    "not working",
    "I don't understand why",
    "!!",
)
_OVERLOAD_MARKERS = (
    "too much",
    "overwhelmed",
    "I can't keep up",
    "slow down",
    "back up",
    "one thing at a time",
    "confused",
    "too many",
)
_DRIFTING_MARKERS = (
    "what were we",
    "I forgot",
    "where were we",
    "lost track",
    "what's the goal",
    "remind me",
    "what was the plan",
)
_CURIOSITY_MARKERS = (
    "interesting",
    "what if",
    "I wonder",
    "tell me more",
    "?",
)

_FRUSTRATION_PATTERN = re.compile(
    "|".join(re.escape(marker) for marker in _FRUSTRATION_MARKERS),
    re.IGNORECASE,
)
_OVERLOAD_PATTERN = re.compile(
    "|".join(re.escape(marker) for marker in _OVERLOAD_MARKERS),
    re.IGNORECASE,
)
_DRIFTING_PATTERN = re.compile(
    "|".join(re.escape(marker) for marker in _DRIFTING_MARKERS),
    re.IGNORECASE,
)
_CURIOSITY_PATTERN = re.compile(
    "|".join(re.escape(marker) for marker in _CURIOSITY_MARKERS),
    re.IGNORECASE,
)


@dataclass
class UserState:
    affect: str = AFFECT_NEUTRAL
    interaction_count: int = 0
    frustration_run: int = 0
    incubation_items: deque = field(
        default_factory=lambda: deque(maxlen=INCUBATION_MAXLEN)
    )
    last_updated: datetime | None = None
    last_bid_content: str | None = None


@dataclass(frozen=True)
class MirrorUserBid:
    coordinator_name: str
    content: str
    timestamp: float
    priority: int = MIRROR_USER_PRIORITY
    source: str = "mirror_user"
    type: str = "state_signal"


Clock = Callable[[], datetime]


class MirrorUser(Coordinator):
    name = "mirror_user"

    def __init__(self, clock: Clock | None = None) -> None:
        self.clock = clock or (lambda: datetime.now(UTC))
        self.state = UserState()

    def observe(self, text: str) -> str:
        affect = _detect_affect(text)
        self.state.interaction_count += 1
        self.state.affect = affect
        if affect == AFFECT_FRUSTRATED:
            self.state.frustration_run += 1
        elif affect != AFFECT_OVERLOADED:
            self.state.frustration_run = 0
        self.state.last_updated = self.clock()
        return affect

    def incubate(self, question: str) -> None:
        self.state.incubation_items.append(question)

    async def background_tick(
        self,
        awareness_queue,
        mirror_user_queue=None,
    ) -> None:
        self._drain_incubation_queue(mirror_user_queue)
        observation = _build_observation(self.state)
        if not observation:
            return
        if observation == self.state.last_bid_content:
            return

        _submit_mirror_user_bid(awareness_queue, observation)
        self.state.last_bid_content = observation

    def process(self, packet: dict) -> dict:
        text = _first_text(packet)
        if text:
            self.observe(text)
        packet["mirror_user_affect"] = self.state.affect
        return packet

    def _drain_incubation_queue(self, mirror_user_queue) -> None:
        if mirror_user_queue is None:
            return

        while True:
            try:
                item = mirror_user_queue.get_nowait()
            except (asyncio.QueueEmpty, queue.Empty):
                return
            self.incubate(str(item))
            task_done = getattr(mirror_user_queue, "task_done", None)
            if callable(task_done):
                try:
                    task_done()
                except ValueError:
                    pass


def _detect_affect(text: str) -> str:
    if _OVERLOAD_PATTERN.search(text):
        return AFFECT_OVERLOADED
    if _FRUSTRATION_PATTERN.search(text):
        return AFFECT_FRUSTRATED
    if _DRIFTING_PATTERN.search(text):
        return AFFECT_DRIFTING
    if _CURIOSITY_PATTERN.search(text):
        return AFFECT_CURIOUS
    return AFFECT_FOCUSED


def _build_observation(state: UserState) -> str | None:
    if state.frustration_run >= 3:
        return (
            "Frustration pattern detected — "
            f"{state.frustration_run} consecutive signals. "
            "Consider pausing or changing approach."
        )
    if state.affect == AFFECT_OVERLOADED:
        return (
            "Cognitive load signal detected — consider narrowing focus before "
            "continuing."
        )
    if state.affect == AFFECT_DRIFTING:
        return (
            "Drift signal detected — user may have lost the thread. "
            "Consider reorienting."
        )
    return None


def _submit_mirror_user_bid(awareness_queue, observation: str) -> None:
    bid = MirrorUserBid(
        coordinator_name="mirror_user",
        content=observation,
        timestamp=time.time(),
    )
    submit = getattr(awareness_queue, "submit", None)
    if callable(submit):
        submit(bid)
        return

    put_nowait = getattr(awareness_queue, "put_nowait", None)
    if callable(put_nowait):
        put_nowait(bid)
        return

    raise TypeError("awareness_queue must expose submit() or put_nowait()")


def _first_text(packet: dict) -> str | None:
    for key in ("message", "reason_output"):
        value = packet.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None
