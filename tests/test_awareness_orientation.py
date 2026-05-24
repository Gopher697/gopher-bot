"""
tests/test_awareness_orientation.py

Integration tests for Orientation wiring inside Awareness.synchronous_run().
No Neo4j connection required -- uses mock coordinators.
"""
from __future__ import annotations

import pytest

from coordinators.awareness import Awareness
from coordinators.base import Coordinator


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class _NoopCoordinator(Coordinator):
    """Passes packet through unchanged."""
    name = "noop"

    def process(self, packet: dict) -> dict:
        return packet


class _MockOrientation(Coordinator):
    """Sets known orientation fields for test assertions."""
    name = "orientation"

    def process(self, packet: dict) -> dict:
        packet["orientation"] = {
            "active_goal_focus": "finish the graph substrate",
            "relevant_goals": [],
            "unresolved_items": [],
            "background_pressures": [],
            "thread_context": "Active thread.",
            "operational_context": "Process up 0h1m",
            "recent_shift": "No shift.",
            "do_not_forget": [],
            "recommended_next_pressure": "Continue pursuing the graph substrate.",
        }
        packet["orientation_context"] = "=== ORIENTATION ===\nTest orientation."
        packet["promotable_goal_ids"] = []
        return packet


class _RaisingOrientation(Coordinator):
    """Always raises -- simulates graph unavailability."""
    name = "orientation"

    def process(self, packet: dict) -> dict:
        raise RuntimeError("Neo4j connection refused")


class _MemoryWithContext(Coordinator):
    """Sets a non-empty memory_context so we can test appending."""
    name = "memory"

    def process(self, packet: dict) -> dict:
        packet["memory_context"] = "Prior memory context."
        return packet


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_awareness(orientation=None, memory=None) -> Awareness:
    """Minimal Awareness with all noop coordinators -- no external calls, no Neo4j."""
    return Awareness(
        sensory=_NoopCoordinator(),
        memory=memory or _NoopCoordinator(),
        reason=_NoopCoordinator(),
        voice=_NoopCoordinator(),
        orientation=orientation or _MockOrientation(),
        keeper=_NoopCoordinator(),
        mirror_user=_NoopCoordinator(),
        mirror_self=_NoopCoordinator(),
        ethos=_NoopCoordinator(),
        drive=_NoopCoordinator(),
    )


# ---------------------------------------------------------------------------
# Test 1: Orientation is called and its fields appear in the result
# ---------------------------------------------------------------------------

def test_orientation_fields_present_in_result():
    aw = _make_awareness()
    result = aw.run("hello")
    assert "orientation" in result
    orientation = result["orientation"]
    assert orientation.get("active_goal_focus") == "finish the graph substrate"


# ---------------------------------------------------------------------------
# Test 2: orientation_context is appended to memory_context for Reason
# ---------------------------------------------------------------------------

def test_orientation_context_appended_to_memory_context():
    aw = _make_awareness()
    result = aw.run("what should I focus on?")
    mem_ctx = str(result.get("memory_context") or "")
    assert "ORIENTATION" in mem_ctx
    assert "Test orientation." in mem_ctx


# ---------------------------------------------------------------------------
# Test 3: orientation_context is appended after existing memory_context
# ---------------------------------------------------------------------------

def test_orientation_appended_after_existing_memory_context():
    aw = _make_awareness(memory=_MemoryWithContext())
    result = aw.run("continue")
    mem_ctx = str(result.get("memory_context") or "")
    assert "Prior memory context." in mem_ctx
    assert "ORIENTATION" in mem_ctx
    # Prior context should come before orientation
    assert mem_ctx.index("Prior memory context.") < mem_ctx.index("ORIENTATION")


# ---------------------------------------------------------------------------
# Test 4: Orientation failure does NOT propagate -- pipeline completes
# ---------------------------------------------------------------------------

def test_orientation_failure_is_non_fatal():
    aw = _make_awareness(orientation=_RaisingOrientation())
    # Must not raise -- pipeline continues with orientation absent
    result = aw.run("hello")
    # No hard crash; result is a dict (pipeline completed)
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Test 5: When Orientation raises, orientation key is absent from result
# ---------------------------------------------------------------------------

def test_orientation_absent_when_coordinator_raises():
    aw = _make_awareness(orientation=_RaisingOrientation())
    result = aw.run("hello")
    # orientation key should not be set (orientation.process() never completed)
    assert result.get("orientation") is None


# ---------------------------------------------------------------------------
# Test 6: Awareness instantiates Orientation by default (no explicit arg)
# ---------------------------------------------------------------------------

def test_awareness_instantiates_orientation_by_default():
    aw = Awareness(
        sensory=_NoopCoordinator(),
        memory=_NoopCoordinator(),
        reason=_NoopCoordinator(),
        voice=_NoopCoordinator(),
        keeper=_NoopCoordinator(),
        mirror_user=_NoopCoordinator(),
        mirror_self=_NoopCoordinator(),
        ethos=_NoopCoordinator(),
        drive=_NoopCoordinator(),
        # orientation intentionally omitted -- testing that it defaults to a real Orientation
    )
    assert aw.orientation is not None


# ---------------------------------------------------------------------------
# Test 7: promotable_goal_ids appears in result when orientation runs
# ---------------------------------------------------------------------------

def test_promotable_goal_ids_in_result():
    aw = _make_awareness()
    result = aw.run("what goals are active?")
    assert "promotable_goal_ids" in result
    assert isinstance(result["promotable_goal_ids"], list)


# ---------------------------------------------------------------------------
# Test 8: pipeline still returns a packet without memory_context set
# ---------------------------------------------------------------------------

def test_pipeline_completes_with_no_prior_memory_context():
    # NoopCoordinator does not set memory_context
    aw = _make_awareness()
    result = aw.run("first message ever")
    mem_ctx = str(result.get("memory_context") or "")
    # Orientation context alone is sufficient -- no crash
    assert "ORIENTATION" in mem_ctx


def test_assess_tier_caps_to_local_in_shutdown_mode():
    from coordinators.tier_config import TIER_LOCAL

    aw = _make_awareness()
    packet = {"message": "summarize this", "high_stakes": True, "shutdown_mode": True}
    aw.assess_tier(packet)
    assert packet["tier"] == TIER_LOCAL


def test_assess_tier_adds_tier_name():
    aw = _make_awareness()
    packet = {"message": "hello"}
    aw.assess_tier(packet)
    assert "tier_name" in packet


def test_assess_tier_tier_name_matches_tier():
    from coordinators.tier_config import TIER_STANDARD

    aw = _make_awareness()
    packet = {"message": "what should Gopher-bot remember?", "tier": TIER_STANDARD}
    aw.assess_tier(packet)
    assert packet["tier_name"] == "standard"
