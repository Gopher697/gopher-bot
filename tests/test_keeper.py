"""
tests/test_keeper.py

Pure-Python tests for the Keeper coordinator trust escalation protocol.
No disk I/O, no Neo4j.
"""
from __future__ import annotations

import asyncio

import pytest

from coordinators.base import Coordinator
from coordinators.bid import BidQueue
from coordinators.keeper import (
    KEEPER_CADENCE_SECONDS,
    KEEPER_PRIORITY,
    MIN_CLEAN_NREM_STREAK,
    TRUST_LEVEL_REACTIVE,
    TRUST_LEVEL_SUPERVISED,
    Keeper,
    _build_keeper_context,
    _compute_clean_streak,
)


def run(coro):
    return asyncio.run(coro)


def _clean_entries(count: int) -> list[dict]:
    return [{"audit": {"chain_ok": True}} for _ in range(count)]


class _NoopCoordinator(Coordinator):
    name = "noop"

    def process(self, packet: dict) -> dict:
        return packet


class _MockKeeper(Coordinator):
    name = "keeper"

    def process(self, packet: dict) -> dict:
        packet["trust_level"] = TRUST_LEVEL_SUPERVISED
        packet["keeper_context"] = "trust_level=1 clean_nrem_streak=3 last_demotion=none"
        existing = str(packet.get("memory_context") or "").strip()
        packet["memory_context"] = (
            f"{existing}\n\n{packet['keeper_context']}"
            if existing
            else packet["keeper_context"]
        )
        return packet


class _RecordingReason(Coordinator):
    name = "reason"

    def __init__(self) -> None:
        self.seen_packet: dict | None = None

    def process(self, packet: dict) -> dict:
        self.seen_packet = dict(packet)
        return packet


def test_trust_reactive_by_default():
    keeper = Keeper()
    assert keeper.state.trust_level == TRUST_LEVEL_REACTIVE


def test_trust_elevates_after_clean_streak():
    keeper = Keeper(dream_log_reader=lambda: _clean_entries(MIN_CLEAN_NREM_STREAK))
    run(keeper.background_tick(BidQueue()))
    assert keeper.state.clean_nrem_streak == MIN_CLEAN_NREM_STREAK

    packet = keeper.process({})
    assert packet["trust_level"] == TRUST_LEVEL_SUPERVISED


def test_trust_stays_reactive_with_short_streak():
    keeper = Keeper(dream_log_reader=lambda: _clean_entries(MIN_CLEAN_NREM_STREAK - 1))
    run(keeper.background_tick(BidQueue()))

    packet = keeper.process({})
    assert keeper.state.clean_nrem_streak == MIN_CLEAN_NREM_STREAK - 1
    assert packet["trust_level"] == TRUST_LEVEL_REACTIVE


def test_streak_broken_by_chain_failure():
    entries = [
        {"audit": {"chain_ok": True}},
        {"audit": {"chain_ok": True}},
        {"audit": {"chain_ok": True}},
        {"audit": {"chain_ok": False}},
        {"audit": {"chain_ok": True}},
    ]
    keeper = Keeper(dream_log_reader=lambda: entries)
    run(keeper.background_tick(BidQueue()))

    assert keeper.state.clean_nrem_streak == 1


def test_demoted_on_defender_alert():
    keeper = Keeper()
    keeper.state.trust_level = TRUST_LEVEL_SUPERVISED
    packet = keeper.process({"defender_alerts": ["INNER DEFENDER: chain failure"]})

    assert packet["trust_level"] == TRUST_LEVEL_REACTIVE
    assert keeper.state.clean_nrem_streak == 0
    assert "inner defender" in keeper.state.last_demotion_reason.lower()


def test_no_demotion_when_reactive():
    keeper = Keeper()
    packet = keeper.process({"defender_alerts": ["INNER DEFENDER: chain failure"]})
    assert packet["trust_level"] == TRUST_LEVEL_REACTIVE


def test_defender_alert_blocks_same_turn_elevation():
    keeper = Keeper()
    keeper.state.clean_nrem_streak = MIN_CLEAN_NREM_STREAK
    packet = keeper.process({"defender_alerts": ["INNER DEFENDER: chain failure"]})

    assert packet["trust_level"] == TRUST_LEVEL_REACTIVE


def test_no_demotion_on_empty_alerts():
    keeper = Keeper()
    keeper.state.trust_level = TRUST_LEVEL_SUPERVISED
    packet = keeper.process({"defender_alerts": []})
    assert packet["trust_level"] == TRUST_LEVEL_SUPERVISED


def test_keeper_context_in_packet():
    keeper = Keeper()
    packet = keeper.process({})
    assert "trust_level" in packet
    assert "keeper_context" in packet
    assert packet["keeper_context"] == _build_keeper_context(keeper.state)


def test_keeper_context_appended_to_memory_context():
    keeper = Keeper()
    packet = keeper.process({"memory_context": "prior context"})
    assert "prior context" in packet["memory_context"]
    assert packet["keeper_context"] in packet["memory_context"]


def test_background_tick_updates_streak():
    keeper = Keeper(dream_log_reader=lambda: _clean_entries(4))
    run(keeper.background_tick(BidQueue()))
    assert keeper.state.clean_nrem_streak == 4


def test_background_tick_submits_bid():
    queue = BidQueue()
    keeper = Keeper(dream_log_reader=lambda: _clean_entries(3))
    run(keeper.background_tick(queue))

    assert queue.qsize() == 1
    bid = queue.get_pending()[0]
    assert bid.coordinator_name == "keeper"
    assert bid.priority == KEEPER_PRIORITY


def test_compute_streak_empty():
    assert _compute_clean_streak([]) == 0


def test_compute_streak_all_clean():
    assert _compute_clean_streak(_clean_entries(5)) == 5


def test_compute_streak_one_failure():
    entries = [
        {"audit": {"chain_ok": True}},
        {"audit": {"chain_ok": True}},
        {"audit": {"chain_ok": False}},
        {"audit": {"chain_ok": True}},
        {"audit": {"chain_ok": True}},
    ]
    assert _compute_clean_streak(entries) == 2


def test_compute_streak_failure_is_last():
    entries = _clean_entries(4) + [{"audit": {"chain_ok": False}}]
    assert _compute_clean_streak(entries) == 0


def test_awareness_instantiates_keeper_by_default():
    from coordinators.awareness import Awareness

    awareness = Awareness(
        sensory=_NoopCoordinator(),
        memory=_NoopCoordinator(),
        reason=_NoopCoordinator(),
        voice=_NoopCoordinator(),
        orientation=_NoopCoordinator(),
    )
    assert awareness.keeper is not None


def test_awareness_runs_keeper_before_reason():
    from coordinators.awareness import Awareness

    reason = _RecordingReason()
    awareness = Awareness(
        sensory=_NoopCoordinator(),
        memory=_NoopCoordinator(),
        reason=reason,
        voice=_NoopCoordinator(),
        orientation=_NoopCoordinator(),
        keeper=_MockKeeper(),
    )
    result = awareness.run("hello")

    assert reason.seen_packet is not None
    assert reason.seen_packet["trust_level"] == TRUST_LEVEL_SUPERVISED
    assert result["trust_level"] == TRUST_LEVEL_SUPERVISED


def test_brain_loop_registers_keeper_at_cadence():
    from coordinators.brain_loop import (
        BACKGROUND_COORDINATORS,
        BACKGROUND_INTERVALS,
        _default_background_coordinators,
    )

    assert "keeper" in BACKGROUND_COORDINATORS
    assert BACKGROUND_INTERVALS["keeper"] == pytest.approx(KEEPER_CADENCE_SECONDS)
    assert "keeper" in _default_background_coordinators()
