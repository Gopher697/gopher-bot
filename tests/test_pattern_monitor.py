from __future__ import annotations

import asyncio

from coordinators.bid import PRIORITY_PATTERN, BidQueue
from coordinators.pattern_monitor import PatternMonitor


def test_pattern_monitor_instantiates_and_tick_runs_against_empty_sources():
    queue = BidQueue()
    monitor = PatternMonitor(
        coordinator_log_reader=lambda limit: [],
        training_candidate_reader=lambda: [],
        training_candidate_writer=lambda element_id, score: None,
        god_node_reader=lambda threshold, limit: [],
        pattern_log_writer=lambda entry: None,
    )

    asyncio.run(monitor.background_tick(queue))

    assert queue.get_pending() == []


def test_brain_loop_registers_pattern_monitor_by_default():
    from coordinators.brain_loop import BrainLoop

    brain_loop = BrainLoop()

    assert isinstance(brain_loop.coordinators["pattern_monitor"], PatternMonitor)
    assert brain_loop.intervals["pattern_monitor"] == 90.0


def test_pattern_monitor_flags_low_acceptance_and_scores_training_candidates():
    queue = BidQueue()
    updates = []
    logs = [
        {
            "coordinator_name": "reason",
            "timestamp": float(index),
            "accepted": index < 5,
            "confidence": 0.8,
            "reasoning_trace": None,
        }
        for index in range(20)
    ]
    candidates = [
        {
            "element_id": "episode-1",
            "confidence": 0.75,
            "accepted": True,
            "outcome_quality": None,
        },
        {
            "element_id": "episode-2",
            "confidence": 0.75,
            "accepted": False,
            "outcome_quality": None,
        },
    ]
    monitor = PatternMonitor(
        coordinator_log_reader=lambda limit: logs,
        training_candidate_reader=lambda: candidates,
        training_candidate_writer=lambda element_id, score: updates.append(
            (element_id, score)
        ),
        god_node_reader=lambda threshold, limit: [],
        pattern_log_writer=lambda entry: None,
        time_fn=lambda: 100.0,
    )

    asyncio.run(monitor.background_tick(queue))

    bids = queue.get_pending()
    assert len(bids) == 1
    assert bids[0].coordinator_name == "pattern_monitor"
    assert bids[0].priority == PRIORITY_PATTERN
    assert (
        bids[0].content
        == "Pattern: reason bid acceptance has dropped to 25% — possible miscalibration"
    )
    assert updates == [("episode-1", 0.7), ("episode-2", 0.3)]


def test_pattern_monitor_flags_recurring_reasoning_trace():
    queue = BidQueue()
    logs = [
        {
            "coordinator_name": "reason",
            "timestamp": float(index),
            "accepted": None,
            "confidence": 0.8,
            "reasoning_trace": "check recent failures before acting",
        }
        for index in range(3)
    ]
    monitor = PatternMonitor(
        coordinator_log_reader=lambda limit: logs,
        training_candidate_reader=lambda: [],
        training_candidate_writer=lambda element_id, score: None,
        god_node_reader=lambda threshold, limit: [],
        pattern_log_writer=lambda entry: None,
        time_fn=lambda: 100.0,
    )

    asyncio.run(monitor.background_tick(queue))

    bids = queue.get_pending()
    assert len(bids) == 1
    assert bids[0].content == (
        "Pattern: recurring reasoning trace detected across 3 entries — "
        "possible promotable regularity"
    )
