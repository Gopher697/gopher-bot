from __future__ import annotations

import asyncio
from datetime import UTC, datetime


def _clock(year=2026, month=5, day=19, hour=12):
    return lambda: datetime(year, month, day, hour, tzinfo=UTC)


# observe() / affect detection

def test_neutral_text_returns_focused():
    from coordinators.mirror_chad import MirrorChad

    mirror = MirrorChad(clock=_clock())

    assert mirror.observe("Please update the next coordinator.") == "focused"


def test_frustration_marker_text_returns_frustrated():
    from coordinators.mirror_chad import MirrorChad

    mirror = MirrorChad(clock=_clock())

    assert mirror.observe("ugh this is broken again") == "frustrated"


def test_overload_marker_text_returns_overloaded():
    from coordinators.mirror_chad import MirrorChad

    mirror = MirrorChad(clock=_clock())

    assert mirror.observe("This is too much, slow down.") == "overloaded"


def test_drifting_marker_text_returns_drifting():
    from coordinators.mirror_chad import MirrorChad

    mirror = MirrorChad(clock=_clock())

    assert mirror.observe("Where were we, I lost track") == "drifting"


def test_curiosity_marker_text_returns_curious():
    from coordinators.mirror_chad import MirrorChad

    mirror = MirrorChad(clock=_clock())

    assert mirror.observe("What if we route this differently?") == "curious"


def test_overload_takes_priority_over_frustration_when_both_present():
    from coordinators.mirror_chad import MirrorChad

    mirror = MirrorChad(clock=_clock())

    assert mirror.observe("ugh, this is too much and still broken") == "overloaded"


def test_frustrated_takes_priority_over_drifting_when_both_present():
    from coordinators.mirror_chad import MirrorChad

    mirror = MirrorChad(clock=_clock())

    assert mirror.observe("ugh, where were we, this is broken") == "frustrated"


def test_interaction_count_increments_on_each_observe_call():
    from coordinators.mirror_chad import MirrorChad

    mirror = MirrorChad(clock=_clock())

    mirror.observe("one")
    mirror.observe("two")

    assert mirror.state.interaction_count == 2


def test_frustration_run_increments_on_frustration_observation():
    from coordinators.mirror_chad import MirrorChad

    mirror = MirrorChad(clock=_clock())

    mirror.observe("wrong")
    mirror.observe("still not working")

    assert mirror.state.frustration_run == 2


def test_frustration_run_resets_to_zero_on_non_frustration_observation():
    from coordinators.mirror_chad import MirrorChad

    mirror = MirrorChad(clock=_clock())
    mirror.observe("wrong")

    mirror.observe("Proceed with the implementation.")

    assert mirror.state.frustration_run == 0


def test_frustration_run_does_not_reset_on_overloaded_observation():
    from coordinators.mirror_chad import MirrorChad

    mirror = MirrorChad(clock=_clock())
    mirror.observe("wrong")

    mirror.observe("too much")

    assert mirror.state.frustration_run == 1


def test_last_updated_is_set_after_observe():
    from coordinators.mirror_chad import MirrorChad

    mirror = MirrorChad(clock=_clock())

    mirror.observe("Proceed.")

    assert mirror.state.last_updated == _clock()()


# incubate()

def test_question_is_appended_to_incubation_items():
    from coordinators.mirror_chad import MirrorChad

    mirror = MirrorChad(clock=_clock())

    mirror.incubate("What does this imply?")

    assert list(mirror.state.incubation_items) == ["What does this imply?"]


def test_incubation_items_respects_maxlen_oldest_dropped_when_full():
    from coordinators.mirror_chad import INCUBATION_MAXLEN, MirrorChad

    mirror = MirrorChad(clock=_clock())

    for index in range(INCUBATION_MAXLEN + 1):
        mirror.incubate(f"question {index}")

    assert len(mirror.state.incubation_items) == INCUBATION_MAXLEN
    assert mirror.state.incubation_items[0] == "question 1"


def test_incubate_alone_submits_no_bid_to_any_queue():
    from coordinators.bid import BidQueue
    from coordinators.mirror_chad import MirrorChad

    queue = BidQueue()
    mirror = MirrorChad(clock=_clock())

    mirror.incubate("Let this sit.")

    assert queue.qsize() == 0


def test_multiple_incubations_accumulate_correctly():
    from coordinators.mirror_chad import MirrorChad

    mirror = MirrorChad(clock=_clock())

    mirror.incubate("first")
    mirror.incubate("second")

    assert list(mirror.state.incubation_items) == ["first", "second"]


# background_tick() - bid conditions

def test_frustration_run_below_three_submits_no_bid():
    from coordinators.bid import BidQueue
    from coordinators.mirror_chad import MirrorChad

    queue = BidQueue()
    mirror = MirrorChad(clock=_clock())
    mirror.state.affect = "frustrated"
    mirror.state.frustration_run = 2

    asyncio.run(mirror.background_tick(queue))

    assert queue.qsize() == 0


def test_frustration_run_equal_three_submits_bid():
    from coordinators.bid import BidQueue
    from coordinators.mirror_chad import MirrorChad

    queue = BidQueue()
    mirror = MirrorChad(clock=_clock())
    mirror.state.affect = "frustrated"
    mirror.state.frustration_run = 3

    asyncio.run(mirror.background_tick(queue))

    assert queue.qsize() == 1


def test_frustration_run_greater_than_three_submits_bid():
    from coordinators.bid import BidQueue
    from coordinators.mirror_chad import MirrorChad

    queue = BidQueue()
    mirror = MirrorChad(clock=_clock())
    mirror.state.affect = "frustrated"
    mirror.state.frustration_run = 4

    asyncio.run(mirror.background_tick(queue))

    assert queue.qsize() == 1


def test_overloaded_affect_submits_bid_regardless_of_frustration_run():
    from coordinators.bid import BidQueue
    from coordinators.mirror_chad import MirrorChad

    queue = BidQueue()
    mirror = MirrorChad(clock=_clock())
    mirror.state.affect = "overloaded"
    mirror.state.frustration_run = 0

    asyncio.run(mirror.background_tick(queue))

    assert queue.qsize() == 1


def test_drifting_affect_submits_bid():
    from coordinators.bid import BidQueue
    from coordinators.mirror_chad import MirrorChad

    queue = BidQueue()
    mirror = MirrorChad(clock=_clock())
    mirror.state.affect = "drifting"

    asyncio.run(mirror.background_tick(queue))

    assert queue.qsize() == 1


def test_focused_affect_submits_no_bid():
    from coordinators.bid import BidQueue
    from coordinators.mirror_chad import MirrorChad

    queue = BidQueue()
    mirror = MirrorChad(clock=_clock())
    mirror.state.affect = "focused"

    asyncio.run(mirror.background_tick(queue))

    assert queue.qsize() == 0


def test_curious_affect_submits_no_bid():
    from coordinators.bid import BidQueue
    from coordinators.mirror_chad import MirrorChad

    queue = BidQueue()
    mirror = MirrorChad(clock=_clock())
    mirror.state.affect = "curious"

    asyncio.run(mirror.background_tick(queue))

    assert queue.qsize() == 0


# background_tick() - no-nag

def test_same_observation_on_second_tick_does_not_submit_second_bid():
    from coordinators.bid import BidQueue
    from coordinators.mirror_chad import MirrorChad

    queue = BidQueue()
    mirror = MirrorChad(clock=_clock())
    mirror.state.affect = "overloaded"

    asyncio.run(mirror.background_tick(queue))
    queue.clear()
    asyncio.run(mirror.background_tick(queue))

    assert queue.qsize() == 0


def test_changed_observation_on_second_tick_does_submit_bid():
    from coordinators.bid import BidQueue
    from coordinators.mirror_chad import MirrorChad

    queue = BidQueue()
    mirror = MirrorChad(clock=_clock())
    mirror.state.affect = "overloaded"

    asyncio.run(mirror.background_tick(queue))
    queue.clear()
    mirror.state.affect = "drifting"
    asyncio.run(mirror.background_tick(queue))

    assert queue.qsize() == 1


# background_tick() - bid fields

def test_bid_source_is_mirror_chad():
    from coordinators.bid import BidQueue
    from coordinators.mirror_chad import MirrorChad

    queue = BidQueue()
    mirror = MirrorChad(clock=_clock())
    mirror.state.affect = "overloaded"

    asyncio.run(mirror.background_tick(queue))

    assert queue.get_pending()[0].source == "mirror_chad"


def test_bid_priority_is_mirror_chad_priority_two():
    from coordinators.bid import BidQueue
    from coordinators.mirror_chad import MIRROR_CHAD_PRIORITY, MirrorChad

    queue = BidQueue()
    mirror = MirrorChad(clock=_clock())
    mirror.state.affect = "overloaded"

    asyncio.run(mirror.background_tick(queue))

    assert queue.get_pending()[0].priority == MIRROR_CHAD_PRIORITY == 2


def test_bid_type_is_state_signal():
    from coordinators.bid import BidQueue
    from coordinators.mirror_chad import MirrorChad

    queue = BidQueue()
    mirror = MirrorChad(clock=_clock())
    mirror.state.affect = "overloaded"

    asyncio.run(mirror.background_tick(queue))

    assert queue.get_pending()[0].type == "state_signal"


def test_frustration_bid_content_contains_frustration_pattern():
    from coordinators.bid import BidQueue
    from coordinators.mirror_chad import MirrorChad

    queue = BidQueue()
    mirror = MirrorChad(clock=_clock())
    mirror.state.affect = "frustrated"
    mirror.state.frustration_run = 3

    asyncio.run(mirror.background_tick(queue))

    assert "Frustration pattern" in queue.get_pending()[0].content


def test_overloaded_bid_content_contains_cognitive_load():
    from coordinators.bid import BidQueue
    from coordinators.mirror_chad import MirrorChad

    queue = BidQueue()
    mirror = MirrorChad(clock=_clock())
    mirror.state.affect = "overloaded"

    asyncio.run(mirror.background_tick(queue))

    assert "Cognitive load" in queue.get_pending()[0].content


def test_drifting_bid_content_contains_drift_signal():
    from coordinators.bid import BidQueue
    from coordinators.mirror_chad import MirrorChad

    queue = BidQueue()
    mirror = MirrorChad(clock=_clock())
    mirror.state.affect = "drifting"

    asyncio.run(mirror.background_tick(queue))

    assert "Drift signal" in queue.get_pending()[0].content


# background_tick() - queue draining

def test_wandering_question_in_queue_is_consumed_and_incubated():
    from coordinators.bid import BidQueue
    from coordinators.mirror_chad import MirrorChad

    mirror_queue = asyncio.Queue()
    mirror_queue.put_nowait("wander one")
    mirror = MirrorChad(clock=_clock())

    asyncio.run(mirror.background_tick(BidQueue(), mirror_queue))

    assert list(mirror.state.incubation_items) == ["wander one"]
    assert mirror_queue.empty()


def test_multiple_questions_in_queue_are_all_consumed_in_one_tick():
    from coordinators.bid import BidQueue
    from coordinators.mirror_chad import MirrorChad

    mirror_queue = asyncio.Queue()
    mirror_queue.put_nowait("wander one")
    mirror_queue.put_nowait("wander two")
    mirror = MirrorChad(clock=_clock())

    asyncio.run(mirror.background_tick(BidQueue(), mirror_queue))

    assert list(mirror.state.incubation_items) == ["wander one", "wander two"]
    assert mirror_queue.empty()


def test_empty_queue_causes_no_error_and_no_incubation():
    from coordinators.bid import BidQueue
    from coordinators.mirror_chad import MirrorChad

    mirror = MirrorChad(clock=_clock())

    asyncio.run(mirror.background_tick(BidQueue(), asyncio.Queue()))

    assert list(mirror.state.incubation_items) == []


def test_none_mirror_chad_queue_causes_no_error_and_no_incubation():
    from coordinators.bid import BidQueue
    from coordinators.mirror_chad import MirrorChad

    mirror = MirrorChad(clock=_clock())

    asyncio.run(mirror.background_tick(BidQueue(), None))

    assert list(mirror.state.incubation_items) == []


# process()

def test_process_attaches_mirror_chad_affect_to_returned_packet():
    from coordinators.mirror_chad import MirrorChad

    packet = MirrorChad(clock=_clock()).process({"message": "Proceed."})

    assert packet["mirror_chad_affect"] == "focused"


def test_process_calls_observe_when_message_key_is_present():
    from coordinators.mirror_chad import MirrorChad

    mirror = MirrorChad(clock=_clock())

    mirror.process({"message": "wrong"})

    assert mirror.state.interaction_count == 1
    assert mirror.state.affect == "frustrated"


def test_process_calls_observe_when_reason_output_key_is_present_and_message_absent():
    from coordinators.mirror_chad import MirrorChad

    mirror = MirrorChad(clock=_clock())

    mirror.process({"reason_output": "This is interesting."})

    assert mirror.state.interaction_count == 1
    assert mirror.state.affect == "curious"


def test_process_does_not_crash_when_neither_text_key_is_present():
    from coordinators.mirror_chad import MirrorChad

    packet = MirrorChad(clock=_clock()).process({})

    assert packet["mirror_chad_affect"] == "neutral"


def test_process_mirror_chad_affect_reflects_detected_affect():
    from coordinators.mirror_chad import MirrorChad

    packet = MirrorChad(clock=_clock()).process({"message": "I am overwhelmed"})

    assert packet["mirror_chad_affect"] == "overloaded"


# BrainLoop integration

def test_mirror_chad_queue_is_asyncio_queue_after_brain_loop_init():
    from coordinators.brain_loop import BrainLoop
    from coordinators.mirror_chad import INCUBATION_MAXLEN

    brain_loop = BrainLoop()

    assert isinstance(brain_loop.mirror_chad_queue, asyncio.Queue)
    assert brain_loop.mirror_chad_queue.maxsize == INCUBATION_MAXLEN


def test_mirror_chad_is_registered_in_default_coordinator_registry():
    from coordinators.brain_loop import BrainLoop
    from coordinators.mirror_chad import MirrorChad

    brain_loop = BrainLoop()

    assert isinstance(brain_loop.coordinators["mirror_chad"], MirrorChad)
    assert brain_loop.intervals["mirror_chad"] == 60.0


def test_mirror_chad_background_tick_accepts_mirror_chad_queue():
    from coordinators.brain_loop import _accepts_mirror_queue
    from coordinators.mirror_chad import MirrorChad

    assert _accepts_mirror_queue(MirrorChad(clock=_clock())) is True
