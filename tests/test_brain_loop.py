from __future__ import annotations

import asyncio
from types import SimpleNamespace


def test_bid_queue_submit_drain_and_clear():
    from coordinators.bid import (
        PRIORITY_DRIVE,
        PRIORITY_SAFETY,
        Bid,
        BidQueue,
    )

    queue = BidQueue()
    queue.submit(Bid("drive", "daily check-in", PRIORITY_DRIVE, 30.0))
    queue.submit(Bid("keeper", "safety flag", PRIORITY_SAFETY, 20.0))

    pending = queue.get_pending()

    assert [bid.coordinator_name for bid in pending] == ["keeper", "drive"]
    assert queue.qsize() == 0

    queue.submit(Bid("drive", "later", PRIORITY_DRIVE, 40.0))
    queue.clear()

    assert queue.get_pending() == []


def test_brain_loop_tick_scheduling_uses_configured_intervals():
    from coordinators.base import Coordinator
    from coordinators.bid import BidQueue
    from coordinators.brain_loop import BrainLoop

    current_time = [1000.0]

    class FakeBackground(Coordinator):
        def __init__(self, name):
            self.name = name
            self.calls = []

        def process(self, packet):
            return packet

        async def background_tick(self, bid_queue):
            self.calls.append(current_time[0])

    feeling = FakeBackground("feeling")
    curiosity = FakeBackground("curiosity")
    awareness = SimpleNamespace(
        bid_queue=BidQueue(),
        last_active=current_time[0],
    )
    brain_loop = BrainLoop(
        coordinators={"feeling": feeling, "curiosity": curiosity},
        intervals={"feeling": 30.0, "curiosity": 180.0},
        time_fn=lambda: current_time[0],
        sleep_interval=0,
    )
    brain_loop.bind_awareness(awareness)

    asyncio.run(brain_loop.tick_once())
    assert feeling.calls == [1000.0]
    assert curiosity.calls == [1000.0]

    current_time[0] += 29.0
    asyncio.run(brain_loop.tick_once())
    assert feeling.calls == [1000.0]
    assert curiosity.calls == [1000.0]

    current_time[0] += 1.0
    asyncio.run(brain_loop.tick_once())
    assert feeling.calls == [1000.0, 1030.0]
    assert curiosity.calls == [1000.0]

    current_time[0] += 150.0
    asyncio.run(brain_loop.tick_once())
    assert curiosity.calls == [1000.0, 1180.0]


def test_brain_loop_calls_background_tick_with_shared_bid_queue():
    from coordinators.base import Coordinator
    from coordinators.bid import PRIORITY_PATTERN, Bid, BidQueue
    from coordinators.brain_loop import BrainLoop

    current_time = [2000.0]

    class BiddingCoordinator(Coordinator):
        name = "pattern_monitor"

        def __init__(self):
            self.received_queue = None

        def process(self, packet):
            return packet

        async def background_tick(self, bid_queue):
            self.received_queue = bid_queue
            bid_queue.submit(
                Bid(self.name, "pattern crossed threshold", PRIORITY_PATTERN, current_time[0])
            )

    coordinator = BiddingCoordinator()
    bid_queue = BidQueue()
    awareness = SimpleNamespace(bid_queue=bid_queue, last_active=current_time[0])
    brain_loop = BrainLoop(
        coordinators={"pattern_monitor": coordinator},
        intervals={"pattern_monitor": 120.0},
        time_fn=lambda: current_time[0],
        sleep_interval=0,
    )
    brain_loop.bind_awareness(awareness)

    asyncio.run(brain_loop.tick_once())

    assert coordinator.received_queue is bid_queue
    assert bid_queue.get_pending()[0].content == "pattern crossed threshold"


def test_dream_ticks_only_after_idle_threshold():
    from coordinators.base import Coordinator
    from coordinators.bid import BidQueue
    from coordinators.brain_loop import BrainLoop

    current_time = [5000.0]

    class DreamCoordinator(Coordinator):
        name = "dream"

        def __init__(self):
            self.calls = []

        def process(self, packet):
            return packet

        async def background_tick(self, bid_queue):
            self.calls.append(current_time[0])

    dream = DreamCoordinator()
    awareness = SimpleNamespace(
        bid_queue=BidQueue(),
        last_active=current_time[0] - 299.0,
    )
    brain_loop = BrainLoop(
        coordinators={"dream": dream},
        time_fn=lambda: current_time[0],
        sleep_interval=0,
    )
    brain_loop.bind_awareness(awareness)

    asyncio.run(brain_loop.tick_once())
    assert dream.calls == []

    current_time[0] += 2.0
    asyncio.run(brain_loop.tick_once())
    assert dream.calls == [5002.0]

    current_time[0] += 1.0
    asyncio.run(brain_loop.tick_once())
    assert dream.calls == [5002.0]


def test_brain_status_endpoint_reports_loop_state_without_starting_thread():
    from interface import server

    client = server.app.test_client()

    response = client.get("/brain-status")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["running"] is False
    assert isinstance(payload["last_ticks"], dict)
    assert isinstance(payload["pending_bids"], int)
