from __future__ import annotations

import asyncio

from tests.conftest import isolated_awareness


# ── AffectState.observe() ────────────────────────────────────────────────────

def test_observe_detects_positive_surprise():
    from coordinators.feeling import AffectState

    state = AffectState()
    detected = state.observe("I discovered something interesting today!")
    assert "positive_surprise" in detected
    assert state.scores["positive_surprise"] > 0


def test_observe_detects_negative_surprise():
    from coordinators.feeling import AffectState

    state = AffectState()
    detected = state.observe("There was an error in the pipeline.")
    assert "negative_surprise" in detected
    assert state.scores["negative_surprise"] > 0


def test_observe_detects_curiosity_from_keyword():
    from coordinators.feeling import AffectState

    state = AffectState()
    detected = state.observe("I wonder why this keeps happening.")
    assert "curiosity" in detected


def test_observe_detects_curiosity_from_question_mark():
    from coordinators.feeling import AffectState

    state = AffectState()
    detected = state.observe("What is the best approach?")
    assert "curiosity" in detected


def test_observe_detects_boredom():
    from coordinators.feeling import AffectState

    state = AffectState()
    detected = state.observe("Same thing again, nothing new here.")
    assert "boredom" in detected


def test_observe_returns_empty_for_neutral_text():
    from coordinators.feeling import AffectState

    state = AffectState()
    detected = state.observe("The weather is mild today.")
    assert detected == []


# ── Score increments and ceiling ─────────────────────────────────────────────

def test_observe_increments_score_by_hit_increment():
    from coordinators.feeling import AffectState, HIT_INCREMENT

    state = AffectState()
    state.observe("found something novel")
    assert abs(state.scores["positive_surprise"] - HIT_INCREMENT) < 1e-9


def test_observe_caps_score_at_affect_ceiling():
    from coordinators.feeling import AffectState, AFFECT_CEILING

    state = AffectState()
    for _ in range(20):
        state.observe("error failed broken")
    assert state.scores["negative_surprise"] == AFFECT_CEILING


def test_observe_accumulates_score_across_multiple_calls():
    from coordinators.feeling import AffectState, HIT_INCREMENT

    state = AffectState()
    state.observe("found something novel")
    state.observe("discovered something interesting")
    assert abs(state.scores["positive_surprise"] - 2 * HIT_INCREMENT) < 1e-9


# ── Frustration accumulation ──────────────────────────────────────────────────

def test_frustration_not_triggered_below_threshold():
    from coordinators.feeling import AffectState, FRUSTRATION_RUN_THRESHOLD

    state = AffectState()
    for _ in range(FRUSTRATION_RUN_THRESHOLD - 1):
        state.observe("error occurred")
    assert "frustration" not in [
        k for k, v in state.scores.items() if v > 0
    ] or state.scores["frustration"] == 0


def test_frustration_spikes_after_run_threshold():
    from coordinators.feeling import AffectState, FRUSTRATION_RUN_THRESHOLD, HIT_INCREMENT

    state = AffectState()
    for _ in range(FRUSTRATION_RUN_THRESHOLD):
        state.observe("error failed")
    assert state.scores["frustration"] > 0
    assert state.negative_run >= FRUSTRATION_RUN_THRESHOLD


def test_frustration_appended_to_detected_on_threshold():
    from coordinators.feeling import AffectState, FRUSTRATION_RUN_THRESHOLD

    state = AffectState()
    detected_lists = []
    for _ in range(FRUSTRATION_RUN_THRESHOLD):
        detected_lists.append(state.observe("error failed broken"))
    final_detected = detected_lists[-1]
    assert "frustration" in final_detected


def test_negative_run_decrements_on_non_negative_observation():
    from coordinators.feeling import AffectState

    state = AffectState()
    state.observe("error failed")
    state.observe("error failed")
    assert state.negative_run == 2
    state.observe("all looks fine")
    assert state.negative_run == 1


def test_negative_run_floors_at_zero():
    from coordinators.feeling import AffectState

    state = AffectState()
    state.observe("everything is fine")
    state.observe("all good here")
    assert state.negative_run == 0


# ── AffectState.decay() ───────────────────────────────────────────────────────

def test_decay_reduces_all_scores_by_factor():
    from coordinators.feeling import AffectState, DECAY_FACTOR

    state = AffectState()
    state.observe("error failed")
    state.observe("found something interesting")
    before = dict(state.scores)
    state.decay(now=state._last_decay + 30.0)
    for label in before:
        assert abs(state.scores[label] - before[label] * DECAY_FACTOR) < 1e-9


def test_decay_accepts_now_argument():
    from coordinators.feeling import AffectState, DECAY_FACTOR

    state = AffectState()
    state.observe("error")
    before = state.scores["negative_surprise"]
    state.decay(now=9999.0)
    assert abs(state.scores["negative_surprise"] - before * DECAY_FACTOR) < 1e-9


# ── AffectState.above_threshold() ────────────────────────────────────────────

def test_above_threshold_empty_when_all_below():
    from coordinators.feeling import AffectState

    state = AffectState()
    assert state.above_threshold() == []


def test_above_threshold_returns_correct_affects():
    from coordinators.feeling import AffectState, BID_THRESHOLD, HIT_INCREMENT

    state = AffectState()
    # push negative_surprise above threshold
    hits_needed = int(BID_THRESHOLD / HIT_INCREMENT) + 1
    for _ in range(hits_needed):
        state.observe("error failed")
    notable = state.above_threshold()
    labels = [t[0] for t in notable]
    assert "negative_surprise" in labels


def test_above_threshold_excludes_affects_below_threshold():
    from coordinators.feeling import AffectState, BID_THRESHOLD, HIT_INCREMENT

    state = AffectState()
    state.observe("boring same")
    # boredom gets one hit — likely below threshold
    for label, score in state.above_threshold():
        assert score >= BID_THRESHOLD


# ── AffectState.summary() ────────────────────────────────────────────────────

def test_summary_returns_neutral_when_all_below_01():
    from coordinators.feeling import AffectState

    state = AffectState()
    assert state.summary() == "neutral"


def test_summary_returns_neutral_after_full_decay():
    from coordinators.feeling import AffectState

    state = AffectState()
    state.observe("found something great")
    # decay many times until scores drop below 0.1
    for _ in range(30):
        state.decay()
    assert state.summary() == "neutral"


def test_summary_formats_top_affects():
    from coordinators.feeling import AffectState

    state = AffectState()
    for _ in range(5):
        state.observe("error failed broken")
    summary = state.summary()
    assert "negative_surprise" in summary
    assert "(" in summary and ")" in summary


def test_summary_shows_at_most_three_affects():
    from coordinators.feeling import AffectState

    state = AffectState()
    state.observe("error failed broken")
    state.observe("found interesting novel")
    state.observe("why wonder curious?")
    state.observe("same again repeat")
    parts = state.summary().split(", ")
    assert len(parts) <= 3


# ── AffectState.valence/arousal ──────────────────────────────────────────────

def test_valence_positive_when_positive_surprise_dominates():
    from coordinators.feeling import AffectState

    state = AffectState()
    for _ in range(5):
        state.observe("found something interesting and novel")
    assert state.valence > 0


def test_valence_negative_when_negative_surprise_dominates():
    from coordinators.feeling import AffectState

    state = AffectState()
    for _ in range(5):
        state.observe("error failed broken")
    assert state.valence < 0


def test_arousal_zero_when_neutral():
    from coordinators.feeling import AffectState

    state = AffectState()
    assert state.arousal == 0.0


def test_arousal_positive_when_any_affect_active():
    from coordinators.feeling import AffectState

    state = AffectState()
    state.observe("error failed")
    assert state.arousal > 0.0


# ── Feeling.process() ────────────────────────────────────────────────────────

def test_feeling_process_extracts_message_key():
    from coordinators.feeling import Feeling

    f = Feeling()
    packet = f.process({"message": "I found something interesting"})
    assert "affect_state" in packet


def test_feeling_process_extracts_reason_output_key():
    from coordinators.feeling import Feeling

    f = Feeling()
    packet = f.process({"reason_output": "There was an error in the reasoning."})
    assert "affect_state" in packet
    assert f.state.scores["negative_surprise"] > 0


def test_feeling_process_extracts_error_key():
    from coordinators.feeling import Feeling

    f = Feeling()
    packet = f.process({"error": "pipeline failed"})
    assert f.state.scores["negative_surprise"] > 0


def test_feeling_process_sets_affect_state_string():
    from coordinators.feeling import Feeling

    f = Feeling()
    packet = f.process({"message": "nothing unusual"})
    assert isinstance(packet["affect_state"], str)


def test_feeling_process_returns_packet():
    from coordinators.feeling import Feeling

    f = Feeling()
    original = {"message": "hello", "other_key": 42}
    result = f.process(original)
    assert result is original
    assert result["other_key"] == 42


def test_feeling_process_skips_observe_when_no_text_keys():
    from coordinators.feeling import Feeling

    f = Feeling()
    packet = f.process({"tier": 1})
    assert packet["affect_state"] == "neutral"


# ── Feeling.background_tick() ────────────────────────────────────────────────

def test_background_tick_decays_state():
    from coordinators.bid import BidQueue
    from coordinators.feeling import Feeling, DECAY_FACTOR

    f = Feeling()
    for _ in range(5):
        f.state.observe("error failed broken")
    before = f.state.scores["negative_surprise"]
    asyncio.run(f.background_tick(BidQueue()))
    assert abs(f.state.scores["negative_surprise"] - before * DECAY_FACTOR) < 1e-9


def test_background_tick_submits_bid_when_above_threshold():
    from coordinators.bid import BidQueue
    from coordinators.feeling import Feeling, BID_THRESHOLD as FEEL_BID_THRESHOLD, HIT_INCREMENT

    f = Feeling()
    hits_needed = int(FEEL_BID_THRESHOLD / HIT_INCREMENT) + 1
    for _ in range(hits_needed):
        f.state.observe("error failed broken")
    queue = BidQueue()
    asyncio.run(f.background_tick(queue))
    assert queue.qsize() == 1


def test_background_tick_bid_content_contains_affect_name():
    from coordinators.bid import BidQueue
    from coordinators.feeling import Feeling, HIT_INCREMENT, BID_THRESHOLD

    f = Feeling()
    hits_needed = int(BID_THRESHOLD / HIT_INCREMENT) + 1
    for _ in range(hits_needed):
        f.state.observe("error failed broken")
    queue = BidQueue()
    asyncio.run(f.background_tick(queue))
    bid = queue.get_pending()[0]
    assert "negative_surprise" in bid.content or "frustration" in bid.content
    assert bid.coordinator_name == "feeling"


def test_background_tick_submits_only_one_bid():
    from coordinators.bid import BidQueue
    from coordinators.feeling import Feeling, HIT_INCREMENT, BID_THRESHOLD

    f = Feeling()
    hits_needed = int(BID_THRESHOLD / HIT_INCREMENT) + 1
    for _ in range(hits_needed):
        f.state.observe("error failed broken")
        f.state.observe("found interesting novel")
        f.state.observe("why wonder curious?")
    queue = BidQueue()
    asyncio.run(f.background_tick(queue))
    assert queue.qsize() == 1


def test_background_tick_no_bid_when_below_threshold():
    from coordinators.bid import BidQueue
    from coordinators.feeling import Feeling

    f = Feeling()
    queue = BidQueue()
    asyncio.run(f.background_tick(queue))
    assert queue.qsize() == 0


def test_background_tick_uses_priority_default():
    from coordinators.bid import BidQueue, PRIORITY_DEFAULT
    from coordinators.feeling import Feeling, HIT_INCREMENT, BID_THRESHOLD

    f = Feeling()
    hits_needed = int(BID_THRESHOLD / HIT_INCREMENT) + 1
    for _ in range(hits_needed):
        f.state.observe("error failed broken")
    queue = BidQueue()
    asyncio.run(f.background_tick(queue))
    bid = queue.get_pending()[0]
    assert bid.priority == PRIORITY_DEFAULT


# ── Feeling.observe() ────────────────────────────────────────────────────────

def test_feeling_observe_callable_externally():
    from coordinators.feeling import Feeling

    f = Feeling()
    result = f.observe("I found something interesting")
    assert isinstance(result, list)
    assert "positive_surprise" in result


def test_feeling_observe_updates_state():
    from coordinators.feeling import Feeling

    f = Feeling()
    f.observe("error failed broken")
    assert f.state.scores["negative_surprise"] > 0


# ── Awareness + Feeling integration ──────────────────────────────────────────

def test_awareness_calls_feeling_observe_when_provided():
    from coordinators.awareness import Awareness
    from coordinators.base import Coordinator
    from coordinators.voice import Voice

    observed_texts: list[str] = []

    class FakeFeeling(Coordinator):
        name = "feeling"

        def process(self, packet):
            return packet

        def observe(self, text: str) -> list[str]:
            observed_texts.append(text)
            return []

    class Step(Coordinator):
        def __init__(self, name, key, value):
            self.name = name
            self.key = key
            self.value = value

        def process(self, packet):
            packet[self.key] = self.value
            return packet

    awareness = isolated_awareness(
        sensory=Step("sensory", "keywords", ["test"]),
        memory=Step("memory", "memory_context", "ctx"),
        reason=Step("reason", "reason_output", "response text"),
        voice=Voice(),
        feeling=FakeFeeling(),
    )
    awareness.synchronous_run("hello world")

    assert len(observed_texts) == 1
    assert "response text" in observed_texts[0]


def test_awareness_without_feeling_still_works():
    from coordinators.awareness import Awareness
    from coordinators.base import Coordinator
    from coordinators.voice import Voice

    class Step(Coordinator):
        def __init__(self, name, key, value):
            self.name = name
            self.key = key
            self.value = value

        def process(self, packet):
            packet[self.key] = self.value
            return packet

    awareness = isolated_awareness(
        sensory=Step("sensory", "keywords", ["test"]),
        memory=Step("memory", "memory_context", "ctx"),
        reason=Step("reason", "reason_output", "all fine"),
        voice=Voice(),
        feeling=None,
    )
    packet = awareness.synchronous_run("hello")
    assert packet["final_response"] == "all fine."


def test_awareness_feeling_observe_not_called_on_error_path():
    """When sensory errors out, feeling.observe() should NOT be called
    because the pipeline short-circuits before voice produces a reason_output."""
    from coordinators.awareness import Awareness
    from coordinators.base import Coordinator
    from coordinators.voice import Voice

    observe_calls: list[str] = []

    class FakeFeeling(Coordinator):
        name = "feeling"

        def process(self, packet):
            return packet

        def observe(self, text: str) -> list[str]:
            observe_calls.append(text)
            return []

    class ErrorSensory(Coordinator):
        name = "sensory"

        def process(self, packet):
            packet["error"] = "sensory failed"
            packet["reason_output"] = "fallback"
            return packet

    awareness = isolated_awareness(
        sensory=ErrorSensory(),
        voice=Voice(),
        feeling=FakeFeeling(),
    )
    awareness.synchronous_run("test")
    # The early return path doesn't invoke feeling.observe()
    assert observe_calls == []
