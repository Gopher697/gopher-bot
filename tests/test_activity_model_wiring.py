"""Tests for Activity model Part B - coordinator wiring."""
from __future__ import annotations


class _MemorySink:
    def store(self, observation):
        return None


# ---------------------------------------------------------------------------
# Orientation wiring tests
# ---------------------------------------------------------------------------

def test_orientation_injects_game_activity_into_context():
    """Active game activity appears in orientation_context seen by Reason."""
    from coordinators.orientation import _build_digest, _format_orientation_context

    orientation = _build_digest(
        packet={
            "current_activity": {
                "type": "game",
                "context_key": "chess",
                "skill_domains": ["chess"],
                "state": {
                    "fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR"
                },
            },
        },
        scored_active=[],
        promotable=[],
        deferred=[],
        now_ts=1000.0,
    )
    ctx = _format_orientation_context(orientation)
    assert orientation["current_activity"]["type"] == "game"
    assert "Activity: game [chess]" in ctx
    assert "rnbqkbnr" in ctx
    assert "chess" in ctx


def test_orientation_suppresses_conversation_activity():
    """Conversation activities do not add noise to orientation context."""
    from coordinators.orientation import _format_orientation_context

    orientation = {
        "thread_context": None,
        "operational_context": "Process up 0h1m",
        "active_goal_focus": None,
        "relevant_goals": [],
        "do_not_forget": [],
        "background_pressures": [],
        "recommended_next_pressure": None,
        "recent_shift": None,
        "current_activity": {
            "type": "conversation",
            "context_key": "abc123",
            "skill_domains": [],
            "state": {},
        },
    }
    ctx = _format_orientation_context(orientation)
    assert "Activity:" not in ctx


def test_orientation_injects_reminder_pending_message():
    """Reminder activity shows its message in orientation context."""
    from coordinators.orientation import _format_orientation_context

    orientation = {
        "thread_context": None,
        "operational_context": "Process up 0h1m",
        "active_goal_focus": None,
        "relevant_goals": [],
        "do_not_forget": [],
        "background_pressures": [],
        "recommended_next_pressure": None,
        "recent_shift": None,
        "current_activity": {
            "type": "reminder",
            "context_key": "reminder_1000",
            "skill_domains": [],
            "state": {"message": "check the build logs", "trigger_at": 9999999.0},
        },
    }
    ctx = _format_orientation_context(orientation)
    assert "reminder" in ctx
    assert "check the build logs" in ctx


# ---------------------------------------------------------------------------
# Hands wiring tests
# ---------------------------------------------------------------------------

def test_hands_updates_activity_state_on_successful_action(monkeypatch):
    """Successful whitelist action updates Activity state with last_action."""
    from coordinators.hands import Hands

    updated = []

    def fake_update_activity_state(self_inner, packet, patch):
        updated.append(patch)

    monkeypatch.setattr(Hands, "_update_activity_state", fake_update_activity_state)

    hands = Hands()
    packet = {
        "action": {"type": "search_web", "args": {"query": "activity model"}},
        "current_activity": {
            "type": "game",
            "activity_id": "abc123",
            "skill_domains": ["chess"],
            "state": {},
        },
    }
    hands.process(packet)

    assert len(updated) == 1
    assert updated[0].get("last_action") == "search_web"


def test_hands_skips_activity_update_when_action_blocked(monkeypatch):
    """Blocked actions do not trigger activity state update."""
    from coordinators.hands import Hands

    updated = []

    def fake_update(self_inner, packet, patch):
        updated.append(patch)

    monkeypatch.setattr(Hands, "_update_activity_state", fake_update)

    hands = Hands()
    packet = {
        "action": {"type": "delete_file", "args": {"path": "/tmp/x"}},
        "current_activity": {
            "type": "task",
            "activity_id": "xyz",
            "skill_domains": [],
            "state": {},
        },
    }
    hands.process(packet)
    assert updated == []


# ---------------------------------------------------------------------------
# Reason wiring tests
# ---------------------------------------------------------------------------

def test_reason_records_skill_practice_for_game_activity(monkeypatch):
    """Game activity triggers skill practice recording after response generation."""
    from coordinators.reason import Reason

    recorded = []

    def fake_record(self_inner, activity):
        recorded.append(activity)

    monkeypatch.setattr(Reason, "_record_activity_skills", fake_record)
    monkeypatch.setattr(Reason, "generate_response", lambda *a, **kw: "test response")

    reason = Reason(memory=_MemorySink())
    packet = {
        "message": "what should I do next?",
        "memory_context": "",
        "tier": 1,
        "current_activity": {
            "type": "game",
            "context_key": "chess",
            "activity_id": "abc",
            "skill_domains": ["chess"],
            "state": {},
        },
    }
    reason.process(packet)
    assert len(recorded) == 1
    assert recorded[0]["type"] == "game"


def test_reason_skips_skill_recording_for_conversation(monkeypatch):
    """Conversation activity does not trigger skill recording."""
    from coordinators.reason import Reason

    recorded = []

    def fake_record(self_inner, activity):
        recorded.append(activity)

    monkeypatch.setattr(Reason, "_record_activity_skills", fake_record)
    monkeypatch.setattr(Reason, "generate_response", lambda *a, **kw: "test response")

    reason = Reason(memory=_MemorySink())
    packet = {
        "message": "hello",
        "memory_context": "",
        "tier": 1,
        "current_activity": {
            "type": "conversation",
            "context_key": "default",
            "activity_id": "abc",
            "skill_domains": [],
            "state": {},
        },
    }
    reason.process(packet)
    assert recorded == []


# ---------------------------------------------------------------------------
# Memory wiring tests
# ---------------------------------------------------------------------------

def test_memory_boosts_keywords_from_skill_domains(monkeypatch):
    """Skill domains from current_activity are appended to retrieval keywords."""
    from coordinators.memory import Memory

    captured_keywords = []

    def fake_retrieve(self_inner, keywords, environment="global"):
        captured_keywords.extend(list(keywords))
        return "context"

    monkeypatch.setattr(Memory, "retrieve", fake_retrieve)
    monkeypatch.setattr(Memory, "ingest_attachments", lambda *a, **kw: None)

    mem = Memory()
    packet = {
        "keywords": ["opening", "pawn"],
        "current_activity": {
            "type": "game",
            "skill_domains": ["chess"],
            "state": {},
        },
    }
    mem.process(packet)
    assert "chess" in captured_keywords
    assert "opening" in captured_keywords
    assert "pawn" in captured_keywords


def test_memory_no_boost_for_empty_skill_domains(monkeypatch):
    """Empty skill_domains list does not add keywords."""
    from coordinators.memory import Memory

    captured = []

    def fake_retrieve(self_inner, keywords, environment="global"):
        captured.extend(list(keywords))
        return ""

    monkeypatch.setattr(Memory, "retrieve", fake_retrieve)
    monkeypatch.setattr(Memory, "ingest_attachments", lambda *a, **kw: None)

    mem = Memory()
    packet = {
        "keywords": ["status"],
        "current_activity": {
            "type": "task",
            "skill_domains": [],
            "state": {},
        },
    }
    mem.process(packet)
    assert captured == ["status"]


# ---------------------------------------------------------------------------
# Graph skill domain compatibility
# ---------------------------------------------------------------------------

def test_graph_skill_domains_include_activity_domains():
    """Activity domains emitted by Awareness are valid Skill node domains."""
    from world_models.graph import VALID_SKILL_DOMAINS

    assert "chess" in VALID_SKILL_DOMAINS
    assert "computer_use" in VALID_SKILL_DOMAINS
