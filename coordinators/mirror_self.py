from __future__ import annotations

import json
import time
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

        self._recompute_self_affect()
        self.state.last_updated = self.clock()
        packet["mirror_self_state"] = {
            "self_affect": self.state.self_affect,
            "confidence_map": dict(self.state.confidence_map),
            "open_gaps_proxy": self.state.open_gaps_proxy,
            "session_interaction_count": self.state.session_interaction_count,
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
            "timestamp": self.clock().isoformat(),
        }


def _derive_self_affect(state: SelfState) -> str:
    if state.error_run >= 3:
        return SELF_AFFECT_FRUSTRATED
    if any(value < 0.4 for value in state.confidence_map.values()):
        return SELF_AFFECT_UNCERTAIN
    if state.open_gaps_proxy > 5:
        return SELF_AFFECT_CURIOUS
    if state.session_interaction_count > 0 and state.error_run == 0:
        return SELF_AFFECT_ENGAGED
    return SELF_AFFECT_STABLE


def _build_observation(state: SelfState) -> str | None:
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
    bid = MirrorSelfBid(
        coordinator_name="mirror_self",
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
