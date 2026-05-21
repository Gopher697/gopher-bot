"""
Non-graph tests for the inner defender closed loop:
- Dream bid submission bugs fixed (timestamp + .submit)
- nrem_done_fn wiring in BrainLoop
- defender_alerts separation in Awareness
- inner_defender_log utility
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from queue import Queue

import pytest

from coordinators.bid import PRIORITY_DEFAULT, PRIORITY_SAFETY, Bid, BidQueue
from coordinators.dream import AuditResult, Dream


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(coro):
    return asyncio.run(coro)


def make_dream(**kwargs) -> Dream:
    return Dream(
        driver_fn=lambda: None,
        sleep_window_fn=lambda: False,
        time_fn=lambda: 1_000_000.0,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Bug fix: _submit_nrem_summary uses .submit() and includes timestamp
# ---------------------------------------------------------------------------

def test_nrem_summary_bid_reaches_queue():
    """_submit_nrem_summary now uses .submit() — bid must arrive."""
    from coordinators.dream import NREMResult

    queue = BidQueue()
    dream = make_dream()
    result = NREMResult(ran=True, observations_triaged=3, edges_strengthened=1)
    run(dream._submit_nrem_summary(queue, result))

    assert queue.qsize() == 1
    bid = queue.get_pending()[0]
    assert bid.coordinator_name == "dream"
    assert "NREM complete" in bid.content
    assert bid.priority == PRIORITY_DEFAULT


def test_nrem_summary_bid_has_timestamp():
    """Bid from _submit_nrem_summary must have a numeric timestamp."""
    from coordinators.dream import NREMResult

    queue = BidQueue()
    dream = make_dream()
    result = NREMResult(ran=True)
    run(dream._submit_nrem_summary(queue, result))

    bid = queue.get_pending()[0]
    assert isinstance(bid.timestamp, float)
    assert bid.timestamp > 0


# ---------------------------------------------------------------------------
# Bug fix: _submit_ne_spike uses .submit() and includes timestamp
# ---------------------------------------------------------------------------

def test_ne_spike_bid_reaches_queue():
    """_submit_ne_spike now uses .submit() — bid must arrive."""
    queue = BidQueue()
    dream = make_dream()
    audit = AuditResult(chain_ok=False, chain_error_count=2)
    run(dream._submit_ne_spike(queue, audit))

    assert queue.qsize() == 1
    bid = queue.get_pending()[0]
    assert bid.priority == PRIORITY_SAFETY
    assert "INNER DEFENDER" in bid.content


def test_ne_spike_bid_has_timestamp():
    queue = BidQueue()
    dream = make_dream()
    audit = AuditResult(injection_hits=["jailbreak"])
    run(dream._submit_ne_spike(queue, audit))

    bid = queue.get_pending()[0]
    assert isinstance(bid.timestamp, float)
    assert bid.timestamp > 0


def test_ne_spike_not_submitted_when_clean():
    queue = BidQueue()
    dream = make_dream()
    audit = AuditResult()  # chain_ok=True, no hits
    run(dream._submit_ne_spike(queue, audit))
    assert queue.qsize() == 0


# ---------------------------------------------------------------------------
# nrem_done_fn wiring in BrainLoop
# ---------------------------------------------------------------------------

def test_brain_loop_wires_nrem_done_fn():
    """bind_awareness() sets Dream's nrem_done_fn when it was None."""
    from coordinators.brain_loop import BrainLoop
    from coordinators.awareness import Awareness
    from coordinators.dream import Dream

    dream = Dream()
    assert dream.nrem_done_fn is None

    loop = BrainLoop(coordinators={"dream": dream})
    awareness = Awareness()
    loop.bind_awareness(awareness)

    assert dream.nrem_done_fn is not None


def test_nrem_done_fn_updates_last_nrem_time():
    """nrem_done_fn wired by BrainLoop actually updates awareness.last_nrem_time."""
    from coordinators.brain_loop import BrainLoop
    from coordinators.awareness import Awareness
    from coordinators.dream import Dream

    dream = Dream()
    loop = BrainLoop(coordinators={"dream": dream})
    awareness = Awareness()
    loop.bind_awareness(awareness)

    assert awareness.last_nrem_time == 0.0
    dream.nrem_done_fn(9_999_999.0)
    assert awareness.last_nrem_time == pytest.approx(9_999_999.0)


# ---------------------------------------------------------------------------
# defender_alerts separation in Awareness
# ---------------------------------------------------------------------------

def test_defender_alerts_field_present_in_packet():
    """Every Awareness packet includes a defender_alerts field."""
    from coordinators.awareness import Awareness

    class FakeCoord:
        def process(self, packet):
            return packet

    awareness = Awareness(
        sensory=FakeCoord(), memory=FakeCoord(),
        reason=FakeCoord(), voice=FakeCoord(),
    )
    packet = awareness.run("hello")
    assert "defender_alerts" in packet


def test_safety_bid_goes_to_defender_alerts():
    """A PRIORITY_SAFETY bid in the queue surfaces as defender_alerts."""
    from coordinators.awareness import Awareness

    class FakeCoord:
        def process(self, packet):
            return packet

    awareness = Awareness(
        sensory=FakeCoord(), memory=FakeCoord(),
        reason=FakeCoord(), voice=FakeCoord(),
    )
    # Pre-load a safety bid into the queue.
    awareness.bid_queue.submit(
        Bid(
            coordinator_name="dream",
            content="[INNER DEFENDER — NE SPIKE] chain failure",
            priority=PRIORITY_SAFETY,
            timestamp=time.time(),
        )
    )
    packet = awareness.run("hello")
    assert "INNER DEFENDER" in packet.get("defender_alerts", "")


def test_normal_bid_not_in_defender_alerts():
    """A PRIORITY_DEFAULT bid does NOT appear in defender_alerts."""
    from coordinators.awareness import Awareness

    class FakeCoord:
        def process(self, packet):
            return packet

    awareness = Awareness(
        sensory=FakeCoord(), memory=FakeCoord(),
        reason=FakeCoord(), voice=FakeCoord(),
    )
    awareness.bid_queue.submit(
        Bid(
            coordinator_name="curiosity",
            content="I wonder about something",
            priority=PRIORITY_DEFAULT,
            timestamp=time.time(),
        )
    )
    packet = awareness.run("hello")
    assert packet.get("defender_alerts", "") == ""


# ---------------------------------------------------------------------------
# inner_defender_log utility
# ---------------------------------------------------------------------------

def test_log_defender_activation_writes_jsonl(tmp_path):
    from utils.inner_defender_log import log_defender_activation

    log_path = tmp_path / "inner_defender.jsonl"
    log_defender_activation(
        layer="dream_audit",
        content="chain failure",
        priority=PRIORITY_SAFETY,
        details={"chain_error_count": 1},
        log_path=log_path,
    )

    assert log_path.exists()
    entry = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert entry["layer"] == "dream_audit"
    assert entry["priority"] == PRIORITY_SAFETY
    assert entry["details"]["chain_error_count"] == 1


def test_log_defender_activation_appends(tmp_path):
    from utils.inner_defender_log import log_defender_activation

    log_path = tmp_path / "inner_defender.jsonl"
    log_defender_activation("dream_audit", "hit 1", PRIORITY_SAFETY, log_path=log_path)
    log_defender_activation("pattern_monitor", "hit 2", 5, log_path=log_path)

    lines = [l for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 2
    assert json.loads(lines[1])["layer"] == "pattern_monitor"
