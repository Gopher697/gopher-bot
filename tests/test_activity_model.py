"""Tests for Activity model - Part A (schema, recognition, reminder firing)."""
from __future__ import annotations

import time
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Detection helper tests (unit - no graph, no Awareness instance needed)
# ---------------------------------------------------------------------------

def test_fen_pattern_matches_valid_fen():
    """FEN string in message is detected by the regex."""
    from coordinators.awareness import _fen_pattern

    fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR"
    assert _fen_pattern.search(fen) is not None


def test_fen_pattern_does_not_match_plain_text():
    from coordinators.awareness import _fen_pattern

    assert _fen_pattern.search("Let's play chess today") is None


def test_reminder_pattern_matches_natural_language():
    from coordinators.awareness import _reminder_pattern

    cases = [
        "remind me in 10 minutes to check the server",
        "set a reminder for tomorrow at 9:00",
        "in 2 hours ping me",
    ]
    for msg in cases:
        assert _reminder_pattern.search(msg) is not None, f"Should match: {msg!r}"


def test_parse_reminder_trigger_minutes():
    from coordinators.awareness import _parse_reminder_trigger

    now = 1000.0
    result = _parse_reminder_trigger("remind me in 10 minutes", now)
    assert result == now + 10 * 60


def test_parse_reminder_trigger_hours():
    from coordinators.awareness import _parse_reminder_trigger

    now = 1000.0
    result = _parse_reminder_trigger("in 2 hours send me a note", now)
    assert result == now + 2 * 3600


def test_parse_reminder_trigger_no_match():
    from coordinators.awareness import _parse_reminder_trigger

    assert _parse_reminder_trigger("just a normal message", 1000.0) is None


# ---------------------------------------------------------------------------
# _detect_activity tests (Awareness instance with mocked graph)
# ---------------------------------------------------------------------------

def _make_awareness_no_graph():
    """Return an Awareness with all graph calls stubbed out."""
    from tests.conftest import isolated_awareness

    aw = isolated_awareness()
    return aw


def test_detect_activity_chess_fen(monkeypatch):
    """FEN in message -> game activity, chess context key."""
    aw = _make_awareness_no_graph()

    monkeypatch.setattr("coordinators.awareness._graph.connect", lambda: MagicMock())
    monkeypatch.setattr("coordinators.awareness._graph.close", lambda d: None)
    monkeypatch.setattr(
        "coordinators.awareness._graph.create_activity",
        lambda *a, **kw: None,
    )

    packet = {
        "message": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 1",
        "session_id": "test-session",
    }
    result = aw._detect_activity(packet)
    assert result is not None
    assert result["type"] == "game"
    assert result["context_key"] == "chess"
    assert "chess" in result["skill_domains"]


def test_detect_activity_reminder_intent(monkeypatch):
    """Reminder phrase -> reminder activity type with trigger_at set."""
    aw = _make_awareness_no_graph()

    monkeypatch.setattr("coordinators.awareness._graph.connect", lambda: MagicMock())
    monkeypatch.setattr("coordinators.awareness._graph.close", lambda d: None)
    monkeypatch.setattr(
        "coordinators.awareness._graph.create_activity",
        lambda *a, **kw: None,
    )

    packet = {
        "message": "remind me in 5 minutes to stretch",
        "session_id": "test-session",
    }
    result = aw._detect_activity(packet)
    assert result is not None
    assert result["type"] == "reminder"
    assert result["state"].get("trigger_at") is not None
    assert result["state"]["trigger_at"] > time.time()


def test_detect_activity_fallback_conversation(monkeypatch):
    """No recognized signal -> conversation activity."""
    aw = _make_awareness_no_graph()

    monkeypatch.setattr("coordinators.awareness._graph.connect", lambda: MagicMock())
    monkeypatch.setattr("coordinators.awareness._graph.close", lambda d: None)
    monkeypatch.setattr(
        "coordinators.awareness._graph.create_activity",
        lambda *a, **kw: None,
    )

    packet = {"message": "What is the capital of France?", "session_id": "s1"}
    result = aw._detect_activity(packet)
    assert result is not None
    assert result["type"] == "conversation"


def test_detect_activity_registry_deduplication(monkeypatch):
    """Same FEN signal on second call returns same activity_id (no duplicate CREATE)."""
    aw = _make_awareness_no_graph()

    created = []

    def fake_create(*a, **kw):
        created.append(kw.get("activity_id"))

    monkeypatch.setattr("coordinators.awareness._graph.connect", lambda: MagicMock())
    monkeypatch.setattr("coordinators.awareness._graph.close", lambda d: None)
    monkeypatch.setattr("coordinators.awareness._graph.create_activity", fake_create)
    monkeypatch.setattr(
        "coordinators.awareness._graph.update_activity_status",
        lambda *a, **kw: True,
    )

    fen_msg = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 1"
    packet = {"message": fen_msg, "session_id": "s1"}

    r1 = aw._detect_activity(packet)
    r2 = aw._detect_activity(packet)

    assert r1["activity_id"] == r2["activity_id"]
    assert len(created) == 1


def test_detect_activity_graph_failure_disables_repeated_writes(monkeypatch):
    """Graph failure is cached so later activity detection does not keep blocking."""
    aw = _make_awareness_no_graph()

    created = []

    def fake_create(*a, **kw):
        created.append(kw.get("activity_id"))
        raise RuntimeError("Neo4j unavailable")

    monkeypatch.setattr("coordinators.awareness._activity_graph_disabled_until", 0.0)
    monkeypatch.setattr("coordinators.awareness._ACTIVITY_GRAPH_RETRY_SECONDS", 60.0)
    monkeypatch.setattr("coordinators.awareness._graph.connect", lambda: MagicMock())
    monkeypatch.setattr("coordinators.awareness._graph.close", lambda d: None)
    monkeypatch.setattr("coordinators.awareness._graph.create_activity", fake_create)

    aw._detect_activity({"message": "please click submit", "session_id": "s1"})
    aw._detect_activity({"message": "please click cancel", "session_id": "s1"})

    assert len(created) == 1


# ---------------------------------------------------------------------------
# check_scheduled_activities tests
# ---------------------------------------------------------------------------

def test_reminder_fires_when_due(monkeypatch):
    """Due reminder Activity -> bid submitted to bid_queue."""
    from coordinators.bid import BidQueue

    aw = _make_awareness_no_graph()
    bid_queue = BidQueue()

    import json
    now = time.time()
    due_reminder = {
        "activity_id": "abc123",
        "context_key": "reminder_1000",
        "state": json.dumps({"message": "stretch break", "trigger_at": now - 1}),
        "name": "reminder - stretch - 2026-05-25",
    }

    monkeypatch.setattr("coordinators.awareness._graph.connect", lambda: MagicMock())
    monkeypatch.setattr("coordinators.awareness._graph.close", lambda d: None)
    monkeypatch.setattr(
        "coordinators.awareness._graph.get_due_reminders",
        lambda *a, **kw: [due_reminder],
    )
    monkeypatch.setattr(
        "coordinators.awareness._graph.update_activity_status",
        lambda *a, **kw: True,
    )

    aw.check_scheduled_activities(bid_queue)

    bids = bid_queue.get_pending()
    assert len(bids) == 1
    assert "stretch break" in bids[0].content


def test_no_bids_when_no_due_reminders(monkeypatch):
    """No due reminders -> bid_queue stays empty."""
    from coordinators.bid import BidQueue

    aw = _make_awareness_no_graph()
    bid_queue = BidQueue()

    monkeypatch.setattr("coordinators.awareness._graph.connect", lambda: MagicMock())
    monkeypatch.setattr("coordinators.awareness._graph.close", lambda d: None)
    monkeypatch.setattr(
        "coordinators.awareness._graph.get_due_reminders",
        lambda *a, **kw: [],
    )

    aw.check_scheduled_activities(bid_queue)
    assert bid_queue.empty()
