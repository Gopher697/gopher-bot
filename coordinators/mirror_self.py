from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from coordinators.base import Coordinator


MIRROR_SELF_PRIORITY = 3
MIRROR_SELF_CADENCE_SECONDS = 120
CONFIDENCE_LOW_THRESHOLD = 0.3
CONFIDENCE_DECAY = 0.05
CONFIDENCE_GAIN = 0.02
CONFIDENCE_FLOOR = 0.0
CONFIDENCE_CEILING = 1.0
INITIAL_CONFIDENCE = 0.8

INITIAL_CONFIDENCE_DOMAINS = (
    "coordination",
    "memory",
    "knowledge_graph",
    "user_modeling",
)

SELF_AFFECT_STABLE = "stable"
SELF_AFFECT_ENGAGED = "engaged"
SELF_AFFECT_CURIOUS = "curious"
SELF_AFFECT_UNCERTAIN = "uncertain"
SELF_AFFECT_FRUSTRATED = "frustrated"

# Prediction machine — generative model constants.
PREDICTION_EMA_ALPHA = 0.3
PREDICTION_LOW_ACCURACY_THRESHOLD = 0.20
PREDICTION_LOW_ACCURACY_STREAK_LIMIT = 3
PREDICTION_STOP_WORDS = frozenset({
    "the", "a", "an", "is", "in", "on", "at", "to", "for", "of",
    "and", "or", "but", "with", "i", "you", "we", "it", "this", "that",
    "do", "can", "will", "just", "so", "what", "how", "why",
})

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SELF_STATE_PATH = _PROJECT_ROOT / "world_models" / "mirror_self_state.json"


@dataclass
class SelfState:
    self_affect: str = SELF_AFFECT_STABLE
    confidence_map: dict[str, float] = field(
        default_factory=lambda: {
            domain: INITIAL_CONFIDENCE for domain in INITIAL_CONFIDENCE_DOMAINS
        }
    )
    open_gaps_proxy: int = 0
    session_interaction_count: int = 0
    error_run: int = 0
    last_updated: datetime | None = None
    last_bid_content: str | None = None
    disk_used_bytes: int = 0
    disk_free_bytes: int = 0
    predicted_topic: str = ""
    last_prediction_accuracy: float = 0.0
    prediction_accuracy_ema: float = 0.5
    low_accuracy_streak: int = 0


@dataclass(frozen=True)
class MirrorSelfBid:
    coordinator_name: str
    content: str
    timestamp: float
    priority: int = MIRROR_SELF_PRIORITY
    source: str = "mirror_self"
    type: str = "self_state_signal"


Clock = Callable[[], datetime]
StateWriter = Callable[[dict], None]
StateReader = Callable[[], dict | None]


class MirrorSelf(Coordinator):
    name = "mirror_self"

    def __init__(
        self,
        clock: Clock | None = None,
        state_writer: StateWriter | None = None,
        state_reader: StateReader | None = None,
    ) -> None:
        self.clock = clock or (lambda: datetime.now(UTC))
        self.state_writer = state_writer or _default_state_writer
        self.state_reader = state_reader or _default_state_reader
        self.state = SelfState()
        self._restore_state(self.state_reader())

    def process(self, packet: dict) -> dict:
        message = str(packet.get("message") or "").strip()
        if message and self.state.predicted_topic:
            accuracy = _jaccard_similarity(self.state.predicted_topic, message)
            self.state.last_prediction_accuracy = accuracy
            self.state.prediction_accuracy_ema = (
                PREDICTION_EMA_ALPHA * accuracy
                + (1 - PREDICTION_EMA_ALPHA) * self.state.prediction_accuracy_ema
            )
            if (
                self.state.prediction_accuracy_ema
                < PREDICTION_LOW_ACCURACY_THRESHOLD
            ):
                self.state.low_accuracy_streak += 1
            else:
                self.state.low_accuracy_streak = 0

        orientation = packet.get("orientation") or {}
        active_goal = ""
        recommended = ""
        if isinstance(orientation, dict):
            active_goal = str(orientation.get("active_goal_focus") or "").strip()
            recommended = str(
                orientation.get("recommended_next_pressure") or ""
            ).strip()
        self.state.predicted_topic = active_goal or recommended or ""

        self.state.session_interaction_count += 1

        error_val = packet.get("error")
        if error_val is not None and str(error_val).strip():
            self.state.error_run += 1
            self._adjust_confidence(-CONFIDENCE_DECAY)
        else:
            self.state.error_run = 0
            self._adjust_confidence(CONFIDENCE_GAIN)

        curiosity_gaps = packet.get("curiosity_gaps")
        if isinstance(curiosity_gaps, list):
            self.state.open_gaps_proxy = len(curiosity_gaps)

        # Drive.process must run before MirrorSelf.process for this field to
        # reflect the current foreground packet; otherwise the previous
        # persisted footprint remains in state.
        drive_status = packet.get("drive_budget_status", {})
        if isinstance(drive_status, dict):
            disk_used = drive_status.get("disk_used_bytes", 0)
            disk_free = drive_status.get("disk_free_bytes", 0)
            if isinstance(disk_used, int) and disk_used > 0:
                self.state.disk_used_bytes = disk_used
            if isinstance(disk_free, int) and disk_free > 0:
                self.state.disk_free_bytes = disk_free

        self._recompute_self_affect()
        self.state.last_updated = self.clock()
        packet["mirror_self_state"] = {
            "self_affect": self.state.self_affect,
            "confidence_map": dict(self.state.confidence_map),
            "open_gaps_proxy": self.state.open_gaps_proxy,
            "session_interaction_count": self.state.session_interaction_count,
            "disk_used_bytes": self.state.disk_used_bytes,
            "disk_free_bytes": self.state.disk_free_bytes,
            "predicted_topic": self.state.predicted_topic,
            "last_prediction_accuracy": round(
                self.state.last_prediction_accuracy, 4
            ),
            "prediction_accuracy_ema": round(
                self.state.prediction_accuracy_ema, 4
            ),
            "low_accuracy_streak": self.state.low_accuracy_streak,
        }
        return packet

    async def background_tick(self, awareness_queue) -> None:
        self._recompute_self_affect()
        observation = _build_observation(self.state)
        if not observation:
            return
        if observation == self.state.last_bid_content:
            return

        _submit_mirror_self_bid(awareness_queue, observation)
        self.state.last_bid_content = observation
        self.state_writer(self._snapshot())

    def _restore_state(self, snapshot: dict | None) -> None:
        if not isinstance(snapshot, dict):
            return

        restored_confidence = snapshot.get("confidence_map")
        if isinstance(restored_confidence, dict):
            merged = {
                domain: INITIAL_CONFIDENCE for domain in INITIAL_CONFIDENCE_DOMAINS
            }
            for domain, value in restored_confidence.items():
                try:
                    merged[str(domain)] = _clamp_confidence(float(value))
                except (TypeError, ValueError):
                    continue
            self.state.confidence_map = merged

        open_gaps_proxy = snapshot.get("open_gaps_proxy")
        if isinstance(open_gaps_proxy, int):
            self.state.open_gaps_proxy = max(0, open_gaps_proxy)

        last_bid_content = snapshot.get("last_bid_content")
        if isinstance(last_bid_content, str):
            self.state.last_bid_content = last_bid_content

        disk_used = snapshot.get("disk_used_bytes")
        if isinstance(disk_used, int):
            self.state.disk_used_bytes = max(0, disk_used)
        disk_free = snapshot.get("disk_free_bytes")
        if isinstance(disk_free, int):
            self.state.disk_free_bytes = max(0, disk_free)

        predicted_topic = snapshot.get("predicted_topic")
        if isinstance(predicted_topic, str):
            self.state.predicted_topic = predicted_topic

        last_prediction_accuracy = snapshot.get("last_prediction_accuracy")
        if isinstance(last_prediction_accuracy, (int, float)):
            self.state.last_prediction_accuracy = max(
                0.0, min(1.0, float(last_prediction_accuracy))
            )

        prediction_accuracy_ema = snapshot.get("prediction_accuracy_ema")
        if isinstance(prediction_accuracy_ema, (int, float)):
            self.state.prediction_accuracy_ema = max(
                0.0, min(1.0, float(prediction_accuracy_ema))
            )

        low_accuracy_streak = snapshot.get("low_accuracy_streak")
        if isinstance(low_accuracy_streak, int):
            self.state.low_accuracy_streak = max(0, low_accuracy_streak)

    def _adjust_confidence(self, delta: float) -> None:
        for domain, value in self.state.confidence_map.items():
            self.state.confidence_map[domain] = _clamp_confidence(value + delta)

    def _recompute_self_affect(self) -> None:
        self.state.self_affect = _derive_self_affect(self.state)

    def _snapshot(self) -> dict:
        return {
            "confidence_map": dict(self.state.confidence_map),
            "open_gaps_proxy": self.state.open_gaps_proxy,
            "last_bid_content": self.state.last_bid_content,
            "disk_used_bytes": self.state.disk_used_bytes,
            "disk_free_bytes": self.state.disk_free_bytes,
            "predicted_topic": self.state.predicted_topic,
            "last_prediction_accuracy": self.state.last_prediction_accuracy,
            "prediction_accuracy_ema": self.state.prediction_accuracy_ema,
            "low_accuracy_streak": self.state.low_accuracy_streak,
            "timestamp": self.clock().isoformat(),
        }


def _derive_self_affect(state: SelfState) -> str:
    if state.error_run >= 3:
        return SELF_AFFECT_FRUSTRATED
    disk_total = state.disk_used_bytes + state.disk_free_bytes
    if disk_total > 0 and state.disk_used_bytes / disk_total > 0.95:
        return SELF_AFFECT_FRUSTRATED
    if any(value < 0.4 for value in state.confidence_map.values()):
        return SELF_AFFECT_UNCERTAIN
    if state.open_gaps_proxy > 5:
        return SELF_AFFECT_CURIOUS
    if state.session_interaction_count > 0 and state.error_run == 0:
        return SELF_AFFECT_ENGAGED
    return SELF_AFFECT_STABLE


def _build_observation(state: SelfState) -> str | None:
    if state.low_accuracy_streak >= PREDICTION_LOW_ACCURACY_STREAK_LIMIT:
        return (
            f"World-model accuracy degraded — "
            f"EMA={state.prediction_accuracy_ema:.0%} "
            f"for {state.low_accuracy_streak} consecutive turns. "
            "Generative model may need recalibration."
        )

    for domain in sorted(state.confidence_map):
        value = state.confidence_map[domain]
        if value < CONFIDENCE_LOW_THRESHOLD:
            return (
                f"Confidence in {domain} has dropped to {value:.0%} — "
                "flagging low certainty."
            )

    if state.self_affect == SELF_AFFECT_FRUSTRATED:
        return (
            f"System affect is frustrated — {state.error_run} consecutive "
            "error signals."
        )
    return None


def _submit_mirror_self_bid(awareness_queue, observation: str) -> None:
    import time as _time

    bid = MirrorSelfBid(
        coordinator_name="mirror_self",
        content=observation,
        timestamp=_time.time(),
    )
    awareness_queue.submit(bid)


def _jaccard_similarity(a: str, b: str) -> float:
    """
    Word-level Jaccard similarity between two strings after stop-word removal.
    Returns 0.0 if either string is empty after filtering.
    """
    words_a = {w for w in a.lower().split() if w not in PREDICTION_STOP_WORDS}
    words_b = {w for w in b.lower().split() if w not in PREDICTION_STOP_WORDS}
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def _default_state_writer(snapshot: dict) -> None:
    try:
        _SELF_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SELF_STATE_PATH.write_text(
            json.dumps(snapshot, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    except OSError:
        return


def _default_state_reader() -> dict | None:
    try:
        return json.loads(_SELF_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _clamp_confidence(value: float) -> float:
    return max(CONFIDENCE_FLOOR, min(CONFIDENCE_CEILING, value))
