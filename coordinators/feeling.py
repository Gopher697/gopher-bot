from __future__ import annotations

import logging
import re
import time

from coordinators.base import Coordinator
from coordinators.bid import Bid, BidQueue, PRIORITY_DEFAULT


logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────
DECAY_FACTOR = 0.85
HIT_INCREMENT = 0.6
AFFECT_CEILING = 5.0
BID_THRESHOLD = 1.5
FRUSTRATION_RUN_THRESHOLD = 3

AFFECT_LABELS = (
    "positive_surprise",
    "negative_surprise",
    "curiosity",
    "boredom",
    "frustration",
)

# ── Keyword patterns ─────────────────────────────────────────────────────────
_PATTERNS: dict[str, re.Pattern[str]] = {
    "positive_surprise": re.compile(
        r"\b(discover|found|interesting|unexpected|surprising|novel|learned|great)\b",
        re.IGNORECASE,
    ),
    "negative_surprise": re.compile(
        r"\b(error|fail|failed|broken|wrong|problem|issue|cannot|unable|exception)\b",
        re.IGNORECASE,
    ),
    "curiosity": re.compile(
        r"\b(why|what if|wonder|curious|unknown|gap|unclear)\b|(\?)",
        re.IGNORECASE,
    ),
    "boredom": re.compile(
        r"\b(same|again|repeat|nothing new|already|unchanged)\b",
        re.IGNORECASE,
    ),
}


# ── AffectState ──────────────────────────────────────────────────────────────
class AffectState:
    def __init__(self) -> None:
        self.scores: dict[str, float] = {label: 0.0 for label in AFFECT_LABELS}
        self.negative_run: int = 0
        self._last_decay: float = 0.0

    def observe(self, text: str) -> list[str]:
        detected: list[str] = []

        for label, pattern in _PATTERNS.items():
            if pattern.search(text):
                detected.append(label)
                self.scores[label] = min(
                    self.scores[label] + HIT_INCREMENT, AFFECT_CEILING
                )

        if "negative_surprise" in detected:
            self.negative_run += 1
            if self.negative_run >= FRUSTRATION_RUN_THRESHOLD:
                if "frustration" not in detected:
                    detected.append("frustration")
                self.scores["frustration"] = min(
                    self.scores["frustration"] + HIT_INCREMENT, AFFECT_CEILING
                )
        else:
            self.negative_run = max(0, self.negative_run - 1)

        return detected

    def decay(self, now: float | None = None) -> None:
        if now is None:
            now = time.time()
        if self._last_decay == 0.0:
            self._last_decay = now
        elapsed = max(0.0, now - self._last_decay)
        self._last_decay = now
        # scale: full DECAY_FACTOR applied per 30-second tick
        tick_count = elapsed / 30.0
        factor = DECAY_FACTOR ** max(tick_count, 1.0)
        for label in AFFECT_LABELS:
            self.scores[label] *= factor

    @property
    def valence(self) -> float:
        """
        Signed valence in [-1, 1].
        Positive pole: positive_surprise.
        Negative pole: negative_surprise + frustration.
        Normalised by AFFECT_CEILING.
        """
        positive = self.scores["positive_surprise"]
        negative = self.scores["negative_surprise"] + self.scores["frustration"]
        raw = (positive - negative) / AFFECT_CEILING
        return max(-1.0, min(1.0, raw))

    @property
    def arousal(self) -> float:
        """
        Unsigned arousal in [0, 1].
        High when any affect is active.
        Normalised by (AFFECT_CEILING * number of labels).
        """
        total = sum(self.scores.values())
        return min(1.0, total / (AFFECT_CEILING * len(AFFECT_LABELS)))

    def above_threshold(self) -> list[tuple[str, float]]:
        return [
            (label, score)
            for label, score in self.scores.items()
            if score >= BID_THRESHOLD
        ]

    def summary(self) -> str:
        active = [
            (label, score)
            for label, score in self.scores.items()
            if score >= 0.1
        ]
        if not active:
            return "neutral"
        top3 = sorted(active, key=lambda t: t[1], reverse=True)[:3]
        return ", ".join(f"{label} ({score:.2f})" for label, score in top3)


# ── Feeling coordinator ──────────────────────────────────────────────────────
class Feeling(Coordinator):
    name = "feeling"

    def __init__(
        self,
        state: AffectState | None = None,
        time_fn=time.time,
    ) -> None:
        self.state = state or AffectState()
        self._time_fn = time_fn

    def process(self, packet: dict) -> dict:
        parts = []
        for key in ("message", "reason_output", "error"):
            val = packet.get(key)
            if val:
                parts.append(str(val).strip())
        text = " ".join(parts)
        if text:
            self.state.observe(text)
        packet["affect_state"] = self.state.summary()
        return packet

    def observe(self, text: str) -> list[str]:
        """External call path for Awareness to hook into after synchronous_run."""
        return self.state.observe(text)

    async def background_tick(self, bid_queue: BidQueue) -> None:
        try:
            now = self._time_fn()
            self.state.decay(now)

            notable = self.state.above_threshold()
            if not notable:
                return

            top_label, top_score = max(notable, key=lambda t: t[1])
            bid_queue.submit(
                Bid(
                    coordinator_name="feeling",
                    priority=PRIORITY_DEFAULT,
                    content=(
                        f"Affect signal: {top_label} ({top_score:.2f}). "
                        f"State: {self.state.summary()}."
                    ),
                    timestamp=now,
                )
            )
        except Exception as e:
            logger.error("feeling background_tick failed: %s", e, exc_info=True)
