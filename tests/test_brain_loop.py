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


def test_brain_loop_writes_enriched_log_entry_for_each_tick():
    from coordinators.base import Coordinator
    from coordinators.bid import BidQueue
    from coordinators.brain_loop import BrainLoop

    current_time = [3000.0]
    log_entries = []

    class FakeBackground(Coordinator):
        name = "feeling"

        def process(self, packet):
            return packet

        async def background_tick(self, bid_queue):
            return None

    awareness = SimpleNamespace(
        bid_queue=BidQueue(),
        last_active=current_time[0],
    )
    brain_loop = BrainLoop(
        coordinators={"feeling": FakeBackground()},
        intervals={"feeling": 30.0},
        time_fn=lambda: current_time[0],
        sleep_interval=0,
        coordinator_log_writer=log_entries.append,
    )
    brain_loop.bind_awareness(awareness)

    asyncio.run(brain_loop.tick_once())

    assert len(log_entries) == 1
    entry = log_entries[0]
    assert entry["coordinator_name"] == "feeling"
    assert entry["timestamp"] == 3000.0
    assert entry["confidence"] == 0.0
    assert entry["accepted"] is None
    assert entry["outcome_quality"] is None
    assert entry["tier_used"] is None
    assert entry["actual_cost_usd"] == 0.0
    assert entry["reasoning_trace"] is None


def test_brain_loop_emits_audit_update_after_each_background_tick():
    from coordinators.base import Coordinator
    from coordinators.bid import BidQueue
    from coordinators.brain_loop import BrainLoop

    current_time = [4000.0]
    audit_updates = []

    class FakeBackground(Coordinator):
        name = "feeling"
        last_confidence = 0.82
        last_tier_used = "tier-2"
        last_actual_cost_usd = 0.003
        last_event = "background_tick"

        def process(self, packet):
            return packet

        async def background_tick(self, bid_queue):
            return None

    awareness = SimpleNamespace(
        bid_queue=BidQueue(),
        last_active=current_time[0],
    )
    brain_loop = BrainLoop(
        coordinators={"feeling": FakeBackground()},
        intervals={"feeling": 30.0},
        time_fn=lambda: current_time[0],
        sleep_interval=0,
        coordinator_log_writer=lambda entry: None,
        audit_event_emitter=audit_updates.append,
    )
    brain_loop.bind_awareness(awareness)

    asyncio.run(brain_loop.tick_once())

    assert audit_updates == [
        {
            "timestamp": 4000.0,
            "coordinator": "feeling",
            "event": "background_tick",
            "confidence": 0.82,
            "tier_used": "tier-2",
            "actual_cost_usd": 0.003,
            "accepted": None,
        }
    ]


def test_brain_loop_surfaces_high_priority_bid_to_voice_proactively():
    from coordinators.awareness import Awareness
    from coordinators.base import Coordinator
    from coordinators.bid import PRIORITY_PATTERN, Bid, BidQueue
    from coordinators.brain_loop import BrainLoop

    current_time = [6000.0]
    emitted = []
    backfilled = []

    class BiddingCoordinator(Coordinator):
        name = "pattern_monitor"

        def process(self, packet):
            return packet

        async def background_tick(self, bid_queue):
            bid_queue.submit(
                Bid(self.name, "Pattern crossed threshold", PRIORITY_PATTERN, current_time[0])
            )

    class FakeVoice(Coordinator):
        name = "voice"

        def process(self, packet):
            packet["final_response"] = f"Voice says: {packet['reason_output']}"
            return packet

    awareness = Awareness(
        voice=FakeVoice(),
        bid_queue=BidQueue(),
        coordinator_log_acceptance_updater=lambda bid, accepted: backfilled.append(
            (bid.coordinator_name, accepted)
        ),
    )
    brain_loop = BrainLoop(
        coordinators={"pattern_monitor": BiddingCoordinator()},
        intervals={"pattern_monitor": 90.0},
        time_fn=lambda: current_time[0],
        sleep_interval=0,
        coordinator_log_writer=lambda entry: None,
        proactive_response_emitter=emitted.append,
    )
    brain_loop.bind_awareness(awareness)

    asyncio.run(brain_loop.tick_once())

    assert brain_loop.proactive_voice_enabled is True
    assert emitted == ["Voice says: Pattern crossed threshold"]
    assert backfilled == [("pattern_monitor", True)]


def test_brain_loop_rate_limits_proactive_voice_outputs():
    from coordinators.awareness import Awareness
    from coordinators.base import Coordinator
    from coordinators.bid import PRIORITY_PATTERN, Bid, BidQueue
    from coordinators.brain_loop import BrainLoop

    current_time = [7000.0]
    emitted = []

    class BiddingCoordinator(Coordinator):
        name = "pattern_monitor"

        def __init__(self):
            self.count = 0

        def process(self, packet):
            return packet

        async def background_tick(self, bid_queue):
            self.count += 1
            bid_queue.submit(
                Bid(
                    self.name,
                    f"Pattern crossed threshold {self.count}",
                    PRIORITY_PATTERN,
                    current_time[0],
                )
            )

    class FakeVoice(Coordinator):
        name = "voice"

        def process(self, packet):
            packet["final_response"] = packet["reason_output"]
            return packet

    awareness = Awareness(
        voice=FakeVoice(),
        bid_queue=BidQueue(),
        coordinator_log_acceptance_updater=lambda bid, accepted: None,
    )
    coordinator = BiddingCoordinator()
    brain_loop = BrainLoop(
        coordinators={"pattern_monitor": coordinator},
        intervals={"pattern_monitor": 0.0},
        time_fn=lambda: current_time[0],
        sleep_interval=0,
        coordinator_log_writer=lambda entry: None,
        proactive_response_emitter=emitted.append,
    )
    brain_loop.bind_awareness(awareness)

    asyncio.run(brain_loop.tick_once())
    current_time[0] += 59.0
    asyncio.run(brain_loop.tick_once())
    current_time[0] += 1.0
    asyncio.run(brain_loop.tick_once())

    assert emitted == [
        "Pattern crossed threshold 1",
        "Pattern crossed threshold 2",
    ]


def test_brain_loop_does_not_surface_low_priority_bids_proactively():
    from coordinators.awareness import Awareness
    from coordinators.base import Coordinator
    from coordinators.bid import PRIORITY_DRIVE, Bid, BidQueue
    from coordinators.brain_loop import BrainLoop

    current_time = [8000.0]
    emitted = []

    class BiddingCoordinator(Coordinator):
        name = "drive"

        def process(self, packet):
            return packet

        async def background_tick(self, bid_queue):
            bid_queue.submit(
                Bid(self.name, "Routine drive check", PRIORITY_DRIVE, current_time[0])
            )

    awareness = Awareness(
        bid_queue=BidQueue(),
        coordinator_log_acceptance_updater=lambda bid, accepted: None,
    )
    brain_loop = BrainLoop(
        coordinators={"drive": BiddingCoordinator()},
        intervals={"drive": 0.0},
        time_fn=lambda: current_time[0],
        sleep_interval=0,
        coordinator_log_writer=lambda entry: None,
        proactive_response_emitter=emitted.append,
    )
    brain_loop.bind_awareness(awareness)

    asyncio.run(brain_loop.tick_once())

    assert emitted == []


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


def test_brain_status_endpoint_includes_neuromodulator_levels(monkeypatch):
    from interface import server

    fake_neuromodulation = SimpleNamespace(
        state=SimpleNamespace(
            channels={
                "DA": SimpleNamespace(tonic=0.5, phasic=0.25),
                "NE": SimpleNamespace(tonic=0.4, phasic=0.0),
                "5HT": SimpleNamespace(tonic=0.6, phasic=0.1),
                "ACh": SimpleNamespace(tonic=0.5, phasic=0.2),
            }
        )
    )
    monkeypatch.setattr(
        server,
        "brain_loop",
        SimpleNamespace(
            running=False,
            last_ticks={},
            coordinators={"neuromodulation": fake_neuromodulation},
        ),
    )

    client = server.app.test_client()

    response = client.get("/brain-status")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["neuromodulators"] == {
        "DA": 0.75,
        "NE": 0.4,
        "5HT": 0.7,
        "ACh": 0.7,
    }


def test_audit_route_serves_read_only_coordinator_activity_panel():
    from interface import server

    client = server.app.test_client()

    response = client.get("/audit")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Coordinator Activity" in html
    assert "Brain Status" in html
    for heading in ("Time", "Coordinator", "Event", "Confidence", "Tier", "Cost", "Accepted"):
        assert f"<th>{heading}</th>" in html
    assert "audit_update" in html
    assert "/audit-log" in html
    assert "DA" in html
    assert "NE" in html
    assert "5HT" in html
    assert "ACh" in html
    assert "<input" not in html


def test_audit_log_endpoint_returns_normalized_recent_entries(monkeypatch):
    from interface import server

    monkeypatch.setattr(
        server,
        "read_coordinator_log_entries",
        lambda limit: [
            {
                "timestamp": 4100.0,
                "coordinator_name": "feeling",
                "event": "tick",
                "confidence": 0.6,
                "tier_used": "tier-1",
                "actual_cost_usd": 0.001,
                "accepted": True,
            }
        ],
    )
    client = server.app.test_client()

    response = client.get("/audit-log?limit=10")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload == {
        "entries": [
            {
                "timestamp": 4100.0,
                "coordinator": "feeling",
                "event": "tick",
                "confidence": 0.6,
                "tier_used": "tier-1",
                "actual_cost_usd": 0.001,
                "accepted": True,
            }
        ]
    }


def test_chat_interface_listens_for_proactive_responses():
    from interface import server

    client = server.app.test_client()

    response = client.get("/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "/socket.io/socket.io.js" in html
    assert 'socket.on("response"' in html
    assert "/proactive-messages" in html


def test_proactive_messages_endpoint_returns_unread_messages(monkeypatch):
    from interface import server

    monkeypatch.setattr(server, "_proactive_messages", [])
    monkeypatch.setattr(server, "_next_proactive_message_id", iter([1, 2]))
    server._emit_proactive_response("First")
    server._emit_proactive_response("Second")

    client = server.app.test_client()

    response = client.get("/proactive-messages?since=1")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload == {"messages": [{"id": 2, "text": "Second"}]}
