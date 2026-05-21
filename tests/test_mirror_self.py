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
        "predicted_topic",
        "last_prediction_accuracy",
        "prediction_accuracy_ema",
        "low_accuracy_streak",
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


# process() - generative-model prediction tracking

def test_jaccard_identical_strings():
    from coordinators.mirror_self import _jaccard_similarity

    assert _jaccard_similarity("task 67 mirror self", "task 67 mirror self") == 1.0


def test_jaccard_no_overlap():
    from coordinators.mirror_self import _jaccard_similarity

    assert _jaccard_similarity("alpha beta", "gamma delta") == 0.0


def test_jaccard_partial_overlap():
    from coordinators.mirror_self import _jaccard_similarity

    score = _jaccard_similarity("task mirror self", "task orientation keeper")
    assert 0.0 < score < 1.0


def test_jaccard_stop_words_filtered():
    from coordinators.mirror_self import _jaccard_similarity

    assert _jaccard_similarity("the mirror", "the keeper") == 0.0


def test_jaccard_empty_after_filter():
    from coordinators.mirror_self import _jaccard_similarity

    assert _jaccard_similarity("the and of", "a an to") == 0.0


def test_prediction_accuracy_computed_when_message_and_prediction_present():
    mirror = _mirror_self()
    mirror.state.predicted_topic = "task 67 mirror self"

    mirror.process({"message": "working on task 67"})

    assert mirror.state.last_prediction_accuracy > 0.0


def test_prediction_accuracy_zero_when_no_prior_prediction():
    mirror = _mirror_self()
    mirror.state.predicted_topic = ""

    mirror.process({"message": "working on task 67"})

    assert mirror.state.last_prediction_accuracy == 0.0


def test_ema_updated_after_turn():
    mirror = _mirror_self()
    mirror.state.predicted_topic = "task mirror self"

    mirror.process({"message": "task mirror self"})

    assert mirror.state.prediction_accuracy_ema > 0.5


def test_low_accuracy_streak_increments():
    mirror = _mirror_self()
    mirror.state.prediction_accuracy_ema = 0.1
    for _ in range(3):
        mirror.state.predicted_topic = "expected topic"
        mirror.process({"message": "unrelated words"})

    assert mirror.state.low_accuracy_streak >= 3


def test_new_prediction_from_orientation_active_goal():
    mirror = _mirror_self()

    mirror.process({
        "orientation": {
            "active_goal_focus": "write the keeper coordinator",
            "recommended_next_pressure": "check audit log",
        },
    })

    assert mirror.state.predicted_topic == "write the keeper coordinator"


def test_new_prediction_falls_back_to_recommended():
    mirror = _mirror_self()

    mirror.process({
        "orientation": {
            "active_goal_focus": "",
            "recommended_next_pressure": "check audit log",
        },
    })

    assert mirror.state.predicted_topic == "check audit log"


def test_new_prediction_empty_when_no_orientation():
    mirror = _mirror_self()

    mirror.process({})

    assert mirror.state.predicted_topic == ""


def test_low_accuracy_observation_emitted_after_streak():
    from coordinators.mirror_self import (
        PREDICTION_LOW_ACCURACY_STREAK_LIMIT,
        _build_observation,
    )

    mirror = _mirror_self()
    mirror.state.low_accuracy_streak = PREDICTION_LOW_ACCURACY_STREAK_LIMIT
    mirror.state.prediction_accuracy_ema = 0.1

    observation = _build_observation(mirror.state)

    assert "World-model accuracy degraded" in observation


def test_predicted_topic_persisted_and_restored():
    mirror = _mirror_self()
    mirror.state.predicted_topic = "test topic"
    mirror.state.last_prediction_accuracy = 0.25
    mirror.state.prediction_accuracy_ema = 0.75
    mirror.state.low_accuracy_streak = 2

    snapshot = mirror._snapshot()
    restored = _mirror_self()
    restored._restore_state(snapshot)

    assert restored.state.predicted_topic == "test topic"
    assert restored.state.prediction_accuracy_ema == pytest.approx(0.75)
    assert restored.state.low_accuracy_streak == 2


def test_submit_bid_calls_submit_directly():
    from coordinators.mirror_self import MirrorSelfBid, _submit_mirror_self_bid

    class Queue:
        def __init__(self):
            self.submitted = []

        def submit(self, bid):
            self.submitted.append(bid)

        def put_nowait(self, bid):
            raise AssertionError("put_nowait should not be called")

    queue = Queue()

    _submit_mirror_self_bid(queue, "prediction degraded")

    assert len(queue.submitted) == 1
    assert isinstance(queue.submitted[0], MirrorSelfBid)


def test_awareness_runs_mirror_self_before_reason():
    from coordinators.awareness import Awareness
    from coordinators.base import Coordinator

    class Noop(Coordinator):
        name = "noop"

        def process(self, packet):
            return packet

    class Orientation(Coordinator):
        name = "orientation"

        def process(self, packet):
            packet["orientation"] = {
                "active_goal_focus": "foreground prediction topic",
                "recommended_next_pressure": "",
            }
            return packet

    class Reason(Coordinator):
        name = "reason"

        def __init__(self):
            self.seen_packet = None

        def process(self, packet):
            self.seen_packet = dict(packet)
            return packet

    reason = Reason()
    awareness = Awareness(
        sensory=Noop(),
        memory=Noop(),
        orientation=Orientation(),
        keeper=Noop(),
        reason=reason,
        voice=Noop(),
        mirror_self=_mirror_self(),
    )

    result = awareness.run("hello")

    assert reason.seen_packet is not None
    assert reason.seen_packet["mirror_self_state"]["predicted_topic"] == (
        "foreground prediction topic"
    )
    assert result["mirror_self_state"]["predicted_topic"] == (
        "foreground prediction topic"
    )


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
