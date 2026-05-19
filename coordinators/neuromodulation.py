from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from coordinators.base import Coordinator


NEUROMODULATION_CADENCE_SECONDS = 30.0
PHASIC_HALF_LIFE_SECONDS = 300.0
PHASIC_FLOOR = 0.005

CHANNEL_DA = "DA"
CHANNEL_NE = "NE"
CHANNEL_5HT = "5HT"
CHANNEL_ACH = "ACh"

CHANNELS = (CHANNEL_DA, CHANNEL_NE, CHANNEL_5HT, CHANNEL_ACH)
DEFAULT_TONIC_LEVELS = {
    CHANNEL_DA: 0.5,
    CHANNEL_NE: 0.4,
    CHANNEL_5HT: 0.6,
    CHANNEL_ACH: 0.5,
}

_CHANNEL_ALIASES = {
    CHANNEL_DA: CHANNEL_DA,
    CHANNEL_NE: CHANNEL_NE,
    CHANNEL_5HT: CHANNEL_5HT,
    CHANNEL_ACH: CHANNEL_ACH,
    "ACH": CHANNEL_ACH,
}

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_NEUROMODULATION_STATE_PATH = (
    _PROJECT_ROOT / "world_models" / "neuromodulation_state.json"
)


@dataclass
class ModulatorChannel:
    tonic: float
    phasic: float = 0.0


@dataclass
class NeuromodulationState:
    channels: dict[str, ModulatorChannel] = field(
        default_factory=lambda: {
            channel: ModulatorChannel(tonic=tonic)
            for channel, tonic in DEFAULT_TONIC_LEVELS.items()
        }
    )


StateWriter = Callable[[dict], None]
StateReader = Callable[[], dict | None]


class Neuromodulation(Coordinator):
    name = "neuromodulation"

    def __init__(
        self,
        state_writer: StateWriter | None = None,
        state_reader: StateReader | None = None,
        tick_interval_seconds: float = NEUROMODULATION_CADENCE_SECONDS,
    ) -> None:
        self.state_writer = state_writer or _default_state_writer
        self.state_reader = state_reader or _default_state_reader
        self.tick_interval_seconds = tick_interval_seconds
        self.state = NeuromodulationState()
        self._restore_state(self.state_reader())

    def process(self, packet: dict) -> dict:
        return packet

    def inject_phasic(self, channel: str, amount: float) -> None:
        normalized = _normalize_channel(channel)
        self._adjust_phasic(normalized, amount)

        if normalized == CHANNEL_DA:
            self._adjust_phasic(CHANNEL_5HT, -amount * 0.4)
        elif normalized == CHANNEL_5HT:
            self._adjust_phasic(CHANNEL_DA, -amount * 0.4)

    def get_output_params(self) -> dict:
        return {
            "learning_rate": self._effective_level(CHANNEL_DA),
            "exploration_bias": self._effective_level(CHANNEL_NE),
            "consolidation_patience": self._effective_level(CHANNEL_5HT),
            "attention": self._effective_level(CHANNEL_ACH),
        }

    async def background_tick(self, bid_queue) -> None:
        self._decay_phasic(self.tick_interval_seconds)
        # TODO: write to SystemState graph node
        self.state_writer(self.snapshot())

    def snapshot(self) -> dict:
        return {
            f"{channel}_tonic": self.state.channels[channel].tonic
            for channel in CHANNELS
        } | {
            f"{channel}_phasic": self.state.channels[channel].phasic
            for channel in CHANNELS
        }

    def _restore_state(self, snapshot: dict | None) -> None:
        if not isinstance(snapshot, dict):
            return

        for channel in CHANNELS:
            tonic_key = f"{channel}_tonic"
            phasic_key = f"{channel}_phasic"

            if tonic_key in snapshot:
                self.state.channels[channel].tonic = _clamp_unit(snapshot[tonic_key])
            if phasic_key in snapshot:
                self.state.channels[channel].phasic = _clamp_unit(snapshot[phasic_key])

    def _adjust_phasic(self, channel: str, amount: float) -> None:
        current = self.state.channels[channel].phasic
        self.state.channels[channel].phasic = _clamp_unit(current + float(amount))

    def _effective_level(self, channel: str) -> float:
        state = self.state.channels[channel]
        return min(1.0, state.tonic + state.phasic)

    def _decay_phasic(self, tick_interval_seconds: float) -> None:
        decay_factor = math.exp(
            -max(0.0, tick_interval_seconds)
            * math.log(2)
            / PHASIC_HALF_LIFE_SECONDS
        )
        for channel in self.state.channels.values():
            channel.phasic *= decay_factor
            if channel.phasic < PHASIC_FLOOR:
                channel.phasic = 0.0


def _default_state_writer(snapshot: dict) -> None:
    try:
        _NEUROMODULATION_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _NEUROMODULATION_STATE_PATH.write_text(
            json.dumps(snapshot, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    except OSError:
        return


def _default_state_reader() -> dict | None:
    try:
        return json.loads(_NEUROMODULATION_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _normalize_channel(channel: str) -> str:
    try:
        return _CHANNEL_ALIASES[channel]
    except KeyError as exc:
        raise ValueError(f"unknown neuromodulation channel: {channel}") from exc


def _clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
