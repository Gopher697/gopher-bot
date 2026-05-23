from __future__ import annotations

import asyncio
import queue
from types import SimpleNamespace


def _gap(question: str, grounded: bool, source: str = "test") -> dict:
    return {"question": question, "grounded": grounded, "source": source}


# ── Gap detection and routing ────────────────────────────────────────────────

def test_grounded_gap_submits_bid_to_awareness_queue():
    from coordinators.bid import BidQueue
    from coordinators.curiosity import Curiosity

    awareness_queue = BidQueue()
    curiosity = Curiosity(gap_detector=lambda: [_gap("What is missing?", True)])

    asyncio.run(curiosity.background_tick(awareness_queue))

    assert awareness_queue.qsize() == 1


def test_grounded_gap_is_appended_to_grounded_queue():
    from coordinators.bid import BidQueue
    from coordinators.curiosity import Curiosity

    curiosity = Curiosity(gap_detector=lambda: [_gap("What is missing?", True)])

    asyncio.run(curiosity.background_tick(BidQueue()))

    assert list(curiosity.state.grounded_queue) == ["What is missing?"]


def test_wandering_gap_does_not_submit_bid_to_awareness_queue():
    from coordinators.bid import BidQueue
    from coordinators.curiosity import Curiosity

    awareness_queue = BidQueue()
    curiosity = Curiosity(gap_detector=lambda: [_gap("Why does this matter?", False)])

    asyncio.run(curiosity.background_tick(awareness_queue))

    assert awareness_queue.qsize() == 0


def test_wandering_gap_is_appended_to_wandering_queue():
    from coordinators.bid import BidQueue
    from coordinators.curiosity import Curiosity

    curiosity = Curiosity(gap_detector=lambda: [_gap("Why does this matter?", False)])

    asyncio.run(curiosity.background_tick(BidQueue()))

    assert list(curiosity.state.wandering_queue) == ["Why does this matter?"]


def test_wandering_gap_routes_to_mirror_user_queue_when_provided():
    from coordinators.bid import BidQueue
    from coordinators.curiosity import Curiosity

    mirror_user_queue = queue.Queue()
    curiosity = Curiosity(gap_detector=lambda: [_gap("Why does this matter?", False)])

    asyncio.run(curiosity.background_tick(BidQueue(), mirror_user_queue))

    assert mirror_user_queue.get_nowait() == "Why does this matter?"


def test_wandering_gap_is_silently_dropped_when_mirror_user_queue_is_none():
    from coordinators.bid import BidQueue
    from coordinators.curiosity import Curiosity

    curiosity = Curiosity(gap_detector=lambda: [_gap("Why does this matter?", False)])

    asyncio.run(curiosity.background_tick(BidQueue(), None))

    assert list(curiosity.state.wandering_queue) == ["Why does this matter?"]


def test_graph_unavailable_fallback_submits_synthetic_bid_to_awareness_queue(monkeypatch):
    from coordinators.bid import BidQueue
    from coordinators.curiosity import Curiosity

    awareness_queue = BidQueue()
    curiosity = Curiosity()
    monkeypatch.setattr(
        curiosity,
        "_graph_gap_detector",
        lambda: (_ for _ in ()).throw(RuntimeError("graph unavailable")),
    )

    asyncio.run(curiosity.background_tick(awareness_queue))

    pending = awareness_queue.get_pending()
    assert len(pending) == 1
    assert pending[0].source == "curiosity"
    assert pending[0].priority == 4


def test_grounded_queue_full_new_grounded_gap_is_dropped_without_bid():
    from coordinators.bid import BidQueue
    from coordinators.curiosity import Curiosity

    awareness_queue = BidQueue()
    curiosity = Curiosity(gap_detector=lambda: [_gap("new gap", True)])
    for index in range(5):
        curiosity.state.grounded_queue.append(f"existing {index}")

    asyncio.run(curiosity.background_tick(awareness_queue))

    assert awareness_queue.qsize() == 0
    assert "new gap" not in curiosity.state.grounded_queue


def test_grounded_queue_full_existing_items_are_not_displaced():
    from coordinators.bid import BidQueue
    from coordinators.curiosity import Curiosity

    curiosity = Curiosity(gap_detector=lambda: [_gap("new gap", True)])
    existing = [f"existing {index}" for index in range(5)]
    curiosity.state.grounded_queue.extend(existing)

    asyncio.run(curiosity.background_tick(BidQueue()))

    assert list(curiosity.state.grounded_queue) == existing


def test_grounded_queue_overflow_enforces_maxlen_five():
    from coordinators.bid import BidQueue
    from coordinators.curiosity import Curiosity

    gaps = [_gap(f"grounded {index}", True) for index in range(6)]
    curiosity = Curiosity(gap_detector=lambda: gaps)

    asyncio.run(curiosity.background_tick(BidQueue()))

    assert len(curiosity.state.grounded_queue) == 5
    assert list(curiosity.state.grounded_queue) == [
        "grounded 0",
        "grounded 1",
        "grounded 2",
        "grounded 3",
        "grounded 4",
    ]


def test_wandering_queue_overflow_enforces_maxlen_twenty():
    from coordinators.bid import BidQueue
    from coordinators.curiosity import Curiosity

    gaps = [_gap(f"wandering {index}", False) for index in range(25)]
    curiosity = Curiosity(gap_detector=lambda: gaps)

    asyncio.run(curiosity.background_tick(BidQueue()))

    assert len(curiosity.state.wandering_queue) == 20
    assert "wandering 0" not in curiosity.state.wandering_queue
    assert "wandering 24" in curiosity.state.wandering_queue


def test_mirror_user_queue_full_drops_wandering_gap_without_error():
    from coordinators.bid import BidQueue
    from coordinators.curiosity import Curiosity

    mirror_user_queue = queue.Queue(maxsize=1)
    mirror_user_queue.put_nowait("already full")
    curiosity = Curiosity(gap_detector=lambda: [_gap("overflow", False)])

    asyncio.run(curiosity.background_tick(BidQueue(), mirror_user_queue))

    assert list(curiosity.state.wandering_queue) == ["overflow"]
    assert mirror_user_queue.qsize() == 1


# ── Bid content ──────────────────────────────────────────────────────────────

def test_bid_source_is_curiosity():
    from coordinators.bid import BidQueue
    from coordinators.curiosity import Curiosity

    awareness_queue = BidQueue()
    curiosity = Curiosity(gap_detector=lambda: [_gap("What is missing?", True)])

    asyncio.run(curiosity.background_tick(awareness_queue))

    assert awareness_queue.get_pending()[0].source == "curiosity"


def test_bid_priority_is_four():
    from coordinators.bid import BidQueue
    from coordinators.curiosity import Curiosity

    awareness_queue = BidQueue()
    curiosity = Curiosity(gap_detector=lambda: [_gap("What is missing?", True)])

    asyncio.run(curiosity.background_tick(awareness_queue))

    assert awareness_queue.get_pending()[0].priority == 4


def test_bid_type_is_grounded_question():
    from coordinators.bid import BidQueue
    from coordinators.curiosity import Curiosity

    awareness_queue = BidQueue()
    curiosity = Curiosity(gap_detector=lambda: [_gap("What is missing?", True)])

    asyncio.run(curiosity.background_tick(awareness_queue))

    assert awareness_queue.get_pending()[0].type == "grounded_question"


def test_bid_content_matches_question_text():
    from coordinators.bid import BidQueue
    from coordinators.curiosity import Curiosity

    awareness_queue = BidQueue()
    curiosity = Curiosity(gap_detector=lambda: [_gap("What is missing?", True)])

    asyncio.run(curiosity.background_tick(awareness_queue))

    assert awareness_queue.get_pending()[0].content == "What is missing?"


# ── State tracking ───────────────────────────────────────────────────────────

def test_gap_count_increments_by_number_of_gaps_returned_by_detector():
    from coordinators.bid import BidQueue
    from coordinators.curiosity import Curiosity

    curiosity = Curiosity(
        gap_detector=lambda: [
            _gap("one", True),
            _gap("two", False),
            _gap("three", False),
        ]
    )

    asyncio.run(curiosity.background_tick(BidQueue()))

    assert curiosity.state.gap_count == 3


def test_last_tick_is_set_after_background_tick():
    from coordinators.bid import BidQueue
    from coordinators.curiosity import Curiosity

    curiosity = Curiosity(gap_detector=lambda: [])

    asyncio.run(curiosity.background_tick(BidQueue()))

    assert curiosity.state.last_tick is not None


def test_last_tick_is_none_before_first_tick():
    from coordinators.curiosity import Curiosity

    curiosity = Curiosity(gap_detector=lambda: [])

    assert curiosity.state.last_tick is None


def test_gap_count_is_zero_before_first_tick():
    from coordinators.curiosity import Curiosity

    curiosity = Curiosity(gap_detector=lambda: [])

    assert curiosity.state.gap_count == 0


# ── process() ────────────────────────────────────────────────────────────────

def test_process_returns_same_packet_and_preserves_data_without_uncertainty_markers():
    from coordinators.curiosity import Curiosity

    curiosity = Curiosity(gap_detector=lambda: [])
    packet = {"message": "This is clear.", "other": 42}

    result = curiosity.process(packet)

    assert result is packet
    assert result["message"] == "This is clear."
    assert result["other"] == 42


def test_process_attaches_curiosity_gaps_key_to_returned_packet():
    from coordinators.curiosity import Curiosity

    packet = {"message": "This is clear."}

    result = Curiosity(gap_detector=lambda: []).process(packet)

    assert "curiosity_gaps" in result


def test_process_detects_i_dont_know_as_uncertainty_marker():
    from coordinators.curiosity import Curiosity

    curiosity = Curiosity(gap_detector=lambda: [])
    packet = curiosity.process({"reason_output": "I don't know yet."})

    assert len(packet["curiosity_gaps"]) == 1


def test_process_detects_question_mark_as_uncertainty_marker():
    from coordinators.curiosity import Curiosity

    curiosity = Curiosity(gap_detector=lambda: [])
    packet = curiosity.process({"message": "What is the missing link?"})

    assert packet["curiosity_gaps"] == ["What is the missing link?"]


def test_process_detects_unclear_as_uncertainty_marker():
    from coordinators.curiosity import Curiosity

    curiosity = Curiosity(gap_detector=lambda: [])
    packet = curiosity.process({"memory_result": "The source is unclear."})

    assert len(packet["curiosity_gaps"]) == 1


def test_process_does_not_submit_bid_to_awareness_queue():
    from coordinators.bid import BidQueue
    from coordinators.curiosity import Curiosity

    awareness_queue = BidQueue()
    curiosity = Curiosity(gap_detector=lambda: [])

    curiosity.process({"message": "What is the missing link?"})

    assert awareness_queue.qsize() == 0


def test_curiosity_gaps_reflects_grounded_queue_contents_at_time_of_call():
    from coordinators.curiosity import Curiosity

    curiosity = Curiosity(gap_detector=lambda: [])
    curiosity.state.grounded_queue.append("existing gap")
    packet = curiosity.process({"message": "No marker here."})

    assert packet["curiosity_gaps"] == ["existing gap"]


# ── Multiple gaps in one tick ────────────────────────────────────────────────

def test_two_grounded_gaps_are_queued_and_submit_two_bids_when_space_exists():
    from coordinators.bid import BidQueue
    from coordinators.curiosity import Curiosity

    gaps = [_gap("first grounded", True), _gap("second grounded", True)]
    awareness_queue = BidQueue()
    curiosity = Curiosity(gap_detector=lambda: gaps)

    asyncio.run(curiosity.background_tick(awareness_queue))

    assert list(curiosity.state.grounded_queue) == [
        "first grounded",
        "second grounded",
    ]
    assert [bid.content for bid in awareness_queue.get_pending()] == [
        "first grounded",
        "second grounded",
    ]


def test_grounded_and_wandering_gap_route_to_separate_streams():
    from coordinators.bid import BidQueue
    from coordinators.curiosity import Curiosity

    gaps = [_gap("grounded question", True), _gap("wandering question", False)]
    awareness_queue = BidQueue()
    mirror_user_queue = queue.Queue()
    curiosity = Curiosity(gap_detector=lambda: gaps)

    asyncio.run(curiosity.background_tick(awareness_queue, mirror_user_queue))

    assert awareness_queue.get_pending()[0].content == "grounded question"
    assert mirror_user_queue.get_nowait() == "wandering question"


# ── BrainLoop integration ────────────────────────────────────────────────────

def test_brain_loop_default_registry_uses_real_curiosity_at_180s_cadence():
    from coordinators.brain_loop import BrainLoop
    from coordinators.curiosity import Curiosity

    brain_loop = BrainLoop()

    assert isinstance(brain_loop.coordinators["curiosity"], Curiosity)
    assert brain_loop.intervals["curiosity"] == 180.0


def test_brain_loop_passes_mirror_user_queue_to_curiosity_when_available():
    from coordinators.bid import BidQueue
    from coordinators.brain_loop import BrainLoop
    from coordinators.curiosity import Curiosity

    current_time = [1000.0]
    awareness_queue = BidQueue()
    mirror_user_queue = queue.Queue()
    curiosity = Curiosity(gap_detector=lambda: [_gap("mirror-bound", False)])
    awareness = SimpleNamespace(
        bid_queue=awareness_queue,
        last_active=current_time[0],
        mirror_user_queue=mirror_user_queue,
    )
    brain_loop = BrainLoop(
        coordinators={"curiosity": curiosity},
        intervals={"curiosity": 180.0},
        time_fn=lambda: current_time[0],
        sleep_interval=0,
    )
    brain_loop.bind_awareness(awareness)

    asyncio.run(brain_loop.tick_once())

    assert mirror_user_queue.get_nowait() == "mirror-bound"
