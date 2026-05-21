from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest


def _clock(year=2026, month=5, day=19, hour=12):
    return lambda: datetime(year, month, day, hour, tzinfo=UTC)


def _mirror_self(**kwargs):
    from coordinators.mirror_self import MirrorSelf

    kwargs.setdefault("clock", _clock())
    kwargs.setdefault("state_writer", lambda _: None)
    kwargs.setdefault("state_reader", lambda: None)
    return MirrorSelf(**kwargs)


# process() - error and confidence

def test_clean_packet_increments_session_interaction_count():
    mirror = _mirror_self()

    mirror.process({})

    assert mirror.state.session_interaction_count == 1


def test_clean_packet_applies_confidence_gain_to_all_domains():
    from coordinators.mirror_self import INITIAL_CONFIDENCE, CONFIDENCE_GAIN

    mirror = _mirror_self()

    mirror.process({})

    assert all(
        value == INITIAL_CONFIDENCE + CONFIDENCE_GAIN
        for value in mirror.state.confidence_map.values()
    )


def test_clean_packet_resets_error_run_to_zero():
    mirror = _mirror_self()
    mirror.state.error_run = 2

    mirror.process({})

    assert mirror.state.error_run == 0


def test_error_packet_increments_error_run():
    mirror = _mirror_self()

    mirror.process({"error": "boom"})

    assert mirror.state.error_run == 1


def test_error_packet_applies_confidence_decay_to_all_domains():
    from coordinators.mirror_self import INITIAL_CONFIDENCE, CONFIDENCE_DECAY

    mirror = _mirror_self()

    mirror.process({"error": "boom"})

    assert all(
        value == INITIAL_CONFIDENCE - CONFIDENCE_DECAY
        for value in mirror.state.confidence_map.values()
    )


def test_multiple_error_packets_accumulate_decay():
    from coordinators.mirror_self import INITIAL_CONFIDENCE, CONFIDENCE_DECAY

    mirror = _mirror_self()

    mirror.process({"error": "boom"})
    mirror.process({"error": "still boom"})

    assert all(
        value == pytest.approx(INITIAL_CONFIDENCE - (CONFIDENCE_DECAY * 2))
        for value in mirror.state.confidence_map.values()
    )


def test_confidence_floors_at_confidence_floor():
    from coordinators.mirror_self import CONFIDENCE_FLOOR

    mirror = _mirror_self()
    mirror.state.confidence_map = {key: 0.01 for key in mirror.state.confidence_map}

    mirror.process({"error": "boom"})

    assert all(value == CONFIDENCE_FLOOR for value in mirror.state.confidence_map.values())


def test_confidence_ceilings_at_confidence_ceiling():
    from coordinators.mirror_self import CONFIDENCE_CEILING

    mirror = _mirror_self()
    mirror.state.confidence_map = {key: 0.99 for key in mirror.state.confidence_map}

    mirror.process({})

    assert all(
        value == CONFIDENCE_CEILING for value in mirror.state.confidence_map.values()
    )


def test_error_none_is_treated_as_clean():
    from coordinators.mirror_self import INITIAL_CONFIDENCE, CONFIDENCE_GAIN

    mirror = _mirror_self()
    mirror.state.error_run = 2

    mirror.process({"error": None})

    assert mirror.state.error_run == 0
    assert all(
        value == INITIAL_CONFIDENCE + CONFIDENCE_GAIN
        for value in mirror.state.confidence_map.values()
    )


def test_error_empty_string_is_treated_as_clean():
    from coordinators.mirror_self import INITIAL_CONFIDENCE, CONFIDENCE_GAIN

    mirror = _mirror_self()
    mirror.state.error_run = 2

    mirror.process({"error": ""})

    assert mirror.state.error_run == 0
    assert all(
        value == INITIAL_CONFIDENCE + CONFIDENCE_GAIN
        for value in mirror.state.confidence_map.values()
    )


# process() - curiosity_gaps

def test_curiosity_gaps_list_sets_open_gaps_proxy_to_list_length():
    mirror = _mirror_self()

    mirror.process({"curiosity_gaps": ["a", "b", "c"]})

    assert mirror.state.open_gaps_proxy == 3


def test_missing_curiosity_gaps_leaves_open_gaps_proxy_unchanged():
    mirror = _mirror_self()
    mirror.state.open_gaps_proxy = 4

    mirror.process({})

    assert mirror.state.open_gaps_proxy == 4


# process() - self_affect derivation

def test_error_run_three_sets_self_affect_frustrated():
    mirror = _mirror_self()

    mirror.process({"error": "one"})
    mirror.process({"error": "two"})
    mirror.process({"error": "three"})

    assert mirror.state.self_affect == "frustrated"


def test_low_confidence_sets_self_affect_uncertain_when_not_frustrated():
    mirror = _mirror_self()
    mirror.state.confidence_map["memory"] = 0.35

    mirror.process({})

    assert mirror.state.self_affect == "uncertain"


def test_open_gaps_above_five_sets_self_affect_curious():
    mirror = _mirror_self()

    mirror.process({"curiosity_gaps": [1, 2, 3, 4, 5, 6]})

    assert mirror.state.self_affect == "curious"


def test_clean_interaction_sets_self_affect_engaged():
    mirror = _mirror_self()

    mirror.process({})

    assert mirror.state.self_affect == "engaged"


def test_fresh_state_self_affect_is_stable():
    mirror = _mirror_self()

    assert mirror.state.self_affect == "stable"


# process() - mirror_self_state attachment

def test_process_attaches_mirror_self_state_key_to_returned_packet():
    mirror = _mirror_self()

    packet = mirror.process({})

    assert "mirror_self_state" in packet


def test_mirror_self_state_contains_expected_keys():
    mirror = _mirror_self()

    packet = mirror.process({})

    assert set(packet["mirror_self_state"]) == {
        "self_affect",
        "confidence_map",
        "open_gaps_proxy",
        "session_interaction_count",
        "disk_used_bytes",
        "disk_free_bytes",
    }


def test_mirror_self_state_confidence_map_reflects_updated_values():
    from coordinators.mirror_self import INITIAL_CONFIDENCE, CONFIDENCE_DECAY

    mirror = _mirror_self()

    packet = mirror.process({"error": "boom"})

    assert all(
        value == INITIAL_CONFIDENCE - CONFIDENCE_DECAY
        for value in packet["mirror_self_state"]["confidence_map"].values()
    )


def test_disk_fields_read_from_packet():
    mirror = _mirror_self()

    mirror.process({
        "drive_budget_status": {
            "disk_used_bytes": 500,
            "disk_free_bytes": 100,
        },
    })

    assert mirror.state.disk_used_bytes == 500
    assert mirror.state.disk_free_bytes == 100


def test_disk_fields_in_mirror_self_state_packet():
    mirror = _mirror_self()

    packet = mirror.process({
        "drive_budget_status": {
            "disk_used_bytes": 500,
            "disk_free_bytes": 100,
        },
    })

    assert packet["mirror_self_state"]["disk_used_bytes"] == 500
    assert packet["mirror_self_state"]["disk_free_bytes"] == 100


def test_disk_fields_persisted_in_snapshot():
    mirror = _mirror_self()
    mirror.state.disk_used_bytes = 999
    mirror.state.disk_free_bytes = 111

    snapshot = mirror._snapshot()

    assert snapshot["disk_used_bytes"] == 999
    assert snapshot["disk_free_bytes"] == 111


def test_disk_fields_restored_from_snapshot():
    mirror = _mirror_self()

    mirror._restore_state({"disk_used_bytes": 888, "disk_free_bytes": 111})

    assert mirror.state.disk_used_bytes == 888
    assert mirror.state.disk_free_bytes == 111


def test_critical_disk_pressure_sets_self_affect_frustrated():
    from coordinators.mirror_self import _derive_self_affect

    mirror = _mirror_self()
    mirror.state.disk_used_bytes = 96
    mirror.state.disk_free_bytes = 4

    assert _derive_self_affect(mirror.state) == "frustrated"


# background_tick() - bid conditions

def test_low_domain_confidence_submits_bid():
    from coordinators.bid import BidQueue

    queue = BidQueue()
    mirror = _mirror_self()
    mirror.state.confidence_map["memory"] = 0.2

    asyncio.run(mirror.background_tick(queue))

    assert queue.qsize() == 1


def test_frustrated_self_affect_without_low_confidence_submits_bid():
    from coordinators.bid import BidQueue

    queue = BidQueue()
    mirror = _mirror_self()
    mirror.state.error_run = 3

    asyncio.run(mirror.background_tick(queue))

    assert queue.qsize() == 1


def test_stable_affect_and_confidence_above_threshold_submits_no_bid():
    from coordinators.bid import BidQueue

    queue = BidQueue()
    mirror = _mirror_self()

    asyncio.run(mirror.background_tick(queue))

    assert queue.qsize() == 0


def test_low_confidence_bid_content_contains_domain_name():
    from coordinators.bid import BidQueue

    queue = BidQueue()
    mirror = _mirror_self()
    mirror.state.confidence_map["memory"] = 0.2

    asyncio.run(mirror.background_tick(queue))

    assert "memory" in queue.get_pending()[0].content


def test_frustrated_bid_content_contains_frustrated():
    from coordinators.bid import BidQueue

    queue = BidQueue()
    mirror = _mirror_self()
    mirror.state.error_run = 3

    asyncio.run(mirror.background_tick(queue))

    assert "frustrated" in queue.get_pending()[0].content


def test_bid_source_is_mirror_self():
    from coordinators.bid import BidQueue

    queue = BidQueue()
    mirror = _mirror_self()
    mirror.state.confidence_map["memory"] = 0.2

    asyncio.run(mirror.background_tick(queue))

    assert queue.get_pending()[0].source == "mirror_self"


def test_bid_priority_is_mirror_self_priority_three():
    from coordinators.bid import BidQueue
    from coordinators.mirror_self import MIRROR_SELF_PRIORITY

    queue = BidQueue()
    mirror = _mirror_self()
    mirror.state.confidence_map["memory"] = 0.2

    asyncio.run(mirror.background_tick(queue))

    assert queue.get_pending()[0].priority == MIRROR_SELF_PRIORITY == 3


def test_bid_type_is_self_state_signal():
    from coordinators.bid import BidQueue

    queue = BidQueue()
    mirror = _mirror_self()
    mirror.state.confidence_map["memory"] = 0.2

    asyncio.run(mirror.background_tick(queue))

    assert queue.get_pending()[0].type == "self_state_signal"


# background_tick() - no-nag

def test_same_observation_on_second_tick_does_not_submit_second_bid():
    from coordinators.bid import BidQueue

    queue = BidQueue()
    mirror = _mirror_self()
    mirror.state.confidence_map["memory"] = 0.2

    asyncio.run(mirror.background_tick(queue))
    queue.clear()
    asyncio.run(mirror.background_tick(queue))

    assert queue.qsize() == 0


def test_changed_observation_on_second_tick_does_submit_bid():
    from coordinators.bid import BidQueue

    queue = BidQueue()
    mirror = _mirror_self()
    mirror.state.confidence_map["coordination"] = 0.2

    asyncio.run(mirror.background_tick(queue))
    queue.clear()
    mirror.state.confidence_map["coordination"] = 0.8
    mirror.state.confidence_map["memory"] = 0.2
    asyncio.run(mirror.background_tick(queue))

    assert queue.qsize() == 1
    assert "memory" in queue.get_pending()[0].content


# background_tick() - state persistence

def test_state_writer_is_called_after_tick_that_produces_bid():
    from coordinators.bid import BidQueue

    snapshots = []
    mirror = _mirror_self(state_writer=snapshots.append)
    mirror.state.confidence_map["memory"] = 0.2

    asyncio.run(mirror.background_tick(BidQueue()))

    assert len(snapshots) == 1


def test_state_writer_snapshot_contains_confidence_map_and_open_gaps_proxy():
    from coordinators.bid import BidQueue

    snapshots = []
    mirror = _mirror_self(state_writer=snapshots.append)
    mirror.state.confidence_map["memory"] = 0.2
    mirror.state.open_gaps_proxy = 7

    asyncio.run(mirror.background_tick(BidQueue()))

    assert "confidence_map" in snapshots[0]
    assert snapshots[0]["open_gaps_proxy"] == 7


def test_state_writer_not_called_when_no_bid_is_submitted():
    from coordinators.bid import BidQueue

    snapshots = []
    mirror = _mirror_self(state_writer=snapshots.append)

    asyncio.run(mirror.background_tick(BidQueue()))

    assert snapshots == []


# state restoration

def test_state_reader_confidence_map_restores_confidence_map():
    mirror = _mirror_self(
        state_reader=lambda: {"confidence_map": {"memory": 0.42}},
    )

    assert mirror.state.confidence_map["memory"] == 0.42


def test_state_reader_none_leaves_defaults_intact():
    from coordinators.mirror_self import INITIAL_CONFIDENCE

    mirror = _mirror_self(state_reader=lambda: None)

    assert all(value == INITIAL_CONFIDENCE for value in mirror.state.confidence_map.values())


def test_new_domains_not_in_restored_state_get_initial_confidence():
    from coordinators.mirror_self import INITIAL_CONFIDENCE

    mirror = _mirror_self(
        state_reader=lambda: {"confidence_map": {"memory": 0.42}},
    )

    assert mirror.state.confidence_map["coordination"] == INITIAL_CONFIDENCE


def test_session_interaction_count_is_not_restored():
    mirror = _mirror_self(
        state_reader=lambda: {"session_interaction_count": 99},
    )

    assert mirror.state.session_interaction_count == 0


def test_error_run_is_not_restored():
    mirror = _mirror_self(
        state_reader=lambda: {"error_run": 99},
    )

    assert mirror.state.error_run == 0


# brain_loop integration

def test_mirror_self_is_in_default_coordinator_registry():
    from coordinators.brain_loop import BrainLoop
    from coordinators.mirror_self import MirrorSelf

    brain_loop = BrainLoop()

    assert isinstance(brain_loop.coordinators["mirror_self"], MirrorSelf)
    assert brain_loop.intervals["mirror_self"] == 120.0


def test_mirror_self_background_tick_has_standard_signature_without_mirror_queue():
    from coordinators.brain_loop import _accepts_mirror_queue

    mirror = _mirror_self()

    assert _accepts_mirror_queue(mirror) is False
