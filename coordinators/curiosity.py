from __future__ import annotations

import asyncio
import queue
import re
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from coordinators.base import Coordinator


GROUNDED_QUEUE_MAXLEN = 5
WANDERING_QUEUE_MAXLEN = 20
CURIOSITY_PRIORITY = 4

_UNCERTAINTY_MARKERS = re.compile(
    r"\bi don['`]t know\b|\bunclear\b|\buncertain\b|\bnot sure\b|\?",
    re.IGNORECASE,
)
_SYNTHETIC_GAPS = (
    "What pattern in the second brain has not been connected yet?",
    "Which recent observation should be revisited when more context exists?",
    "What assumption keeps recurring without enough evidence?",
    "Which part of the system's self-model is still underdeveloped?",
)


@dataclass
class CuriosityState:
    grounded_queue: deque = field(
        default_factory=lambda: deque(maxlen=GROUNDED_QUEUE_MAXLEN)
    )
    wandering_queue: deque = field(
        default_factory=lambda: deque(maxlen=WANDERING_QUEUE_MAXLEN)
    )
    last_tick: datetime | None = None
    gap_count: int = 0


@dataclass(frozen=True)
class CuriosityBid:
    coordinator_name: str
    content: str
    priority: int
    timestamp: float
    source: str
    type: str


GapDetector = Callable[[], list[dict]]


class Curiosity(Coordinator):
    name = "curiosity"

    def __init__(self, gap_detector: GapDetector | None = None) -> None:
        self.state = CuriosityState()
        self.gap_detector = gap_detector or self._default_gap_detector

    async def background_tick(
        self,
        awareness_queue,
        mirror_user_queue=None,
    ) -> None:
        gaps = self.gap_detector()
        self.state.gap_count += len(gaps)
        self.state.last_tick = datetime.now(UTC)

        for gap in gaps:
            question = str(gap.get("question", "")).strip()
            if not question:
                continue

            if bool(gap.get("grounded")):
                if self._append_grounded(question):
                    _submit_awareness_bid(awareness_queue, question)
                continue

            self.state.wandering_queue.append(question)
            if mirror_user_queue is not None:
                _put_nonblocking(mirror_user_queue, question)

    def process(self, packet: dict) -> dict:
        for key in ("message", "reason_output", "memory_result"):
            value = packet.get(key)
            if not value:
                continue
            text = str(value)
            if _UNCERTAINTY_MARKERS.search(text):
                self._append_grounded(_question_from_uncertainty(text))

        packet["curiosity_gaps"] = list(self.state.grounded_queue)
        return packet

    def _append_grounded(self, question: str) -> bool:
        if len(self.state.grounded_queue) >= GROUNDED_QUEUE_MAXLEN:
            return False
        self.state.grounded_queue.append(question)
        return True

    def _default_gap_detector(self) -> list[dict]:
        try:
            return self._graph_gap_detector()
        except Exception:
            index = self.state.gap_count % len(_SYNTHETIC_GAPS)
            return [
                {
                    "question": _SYNTHETIC_GAPS[index],
                    "grounded": True,
                    "source": "synthetic",
                }
            ]

    def _graph_gap_detector(self) -> list[dict]:
        from world_models import config, graph

        driver = graph.connect()
        try:
            with driver.session(database=config.NEO4J_DATABASE) as session:
                result = session.run(
                    """
                    MATCH (node)
                    WHERE
                        (node.confidence IS NOT NULL AND node.confidence < 0.5)
                        OR (node:Observation AND (
                            node.content IS NULL
                            OR node.environment IS NULL
                            OR node.coordinator IS NULL
                        ))
                        OR (node:Entity AND (
                            node.name IS NULL
                            OR node.entity_type IS NULL
                            OR node.environment IS NULL
                        ))
                    RETURN labels(node) AS labels, properties(node) AS properties
                    LIMIT 5
                    """
                )
                return [_gap_from_graph_record(record) for record in result]
        finally:
            driver.close()


def _submit_awareness_bid(awareness_queue, question: str) -> None:
    bid = CuriosityBid(
        coordinator_name="curiosity",
        source="curiosity",
        priority=CURIOSITY_PRIORITY,
        content=question,
        type="grounded_question",
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


def _put_nonblocking(target_queue, item: str) -> None:
    put_nowait = getattr(target_queue, "put_nowait", None)
    if not callable(put_nowait):
        return

    try:
        put_nowait(item)
    except (queue.Full, asyncio.QueueFull):
        return


def _question_from_uncertainty(text: str) -> str:
    snippet = re.sub(r"\s+", " ", text).strip()
    if len(snippet) > 160:
        snippet = f"{snippet[:157]}..."
    if snippet.endswith("?"):
        return snippet
    return f"What needs clarification here: {snippet}?"


def _gap_from_graph_record(record: Any) -> dict:
    labels = ", ".join(record.get("labels", [])) or "node"
    properties = dict(record.get("properties", {}))
    identifier = (
        properties.get("name")
        or properties.get("content")
        or properties.get("environment")
        or "an unnamed graph node"
    )
    identifier = str(identifier)
    if len(identifier) > 100:
        identifier = f"{identifier[:97]}..."
    return {
        "question": f"What should I learn to resolve an incomplete {labels}: {identifier}?",
        "grounded": True,
        "source": "knowledge_graph",
    }
