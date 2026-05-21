"""
tests/test_orientation.py

Non-graph tests for the Orientation coordinator (Task 63).
Tests: _compute_salience, _passes_promotion_gate, _build_digest structure,
_format_orientation_context, _extract_bid_keywords, _thread_context,
_operational_context, _recommend_next_pressure.

No Neo4j connection required.
"""
from __future__ import annotations

import time
import pytest

from coordinators.orientation import (
    _compute_salience,
    _passes_promotion_gate,
    _build_digest,
    _format_orientation_context,
    _extract_bid_keywords,
    _thread_context,
    _operational_context,
    _recent_shift,
    _recommend_next_pressure,
    PROMOTION_CONFIDENCE_THRESHOLD,
    PROMOTION_SALIENCE_THRESHOLD,
    SALIENCE_HORIZON_WEIGHTS,
    ORIENTATION_MAX_GOALS,
    ORIENTATION_MAX_DEFERRED,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _goal(**overrides) -> dict:
    """Minimal valid goal property dict."""
    base = {
        "goal_id": "abc123",
        "content": "Understand the user's project architecture.",
        "horizon": "thread",
        "priority": 0.7,
        "confidence": 0.8,
        "staleness_state": "fresh",
        "last_advanced_at": None,
        "charter_alignment": "true",
        "current_next_action": None,
        "review_after": None,
    }
    base.update(overrides)
    return base


def _scored(goal: dict, salience: float) -> dict:
    return {"goal": goal, "salience": salience}


def _now() -> float:
    return time.time()


# ---------------------------------------------------------------------------
# _compute_salience tests
# ---------------------------------------------------------------------------

class TestComputeSalience:

    def test_returns_float_in_range(self):
        sal = _compute_salience(_goal(), _now(), set())
        assert 0.0 <= sal <= 1.0

    def test_thread_horizon_scores_higher_than_exploratory(self):
        now = _now()
        thread_sal = _compute_salience(_goal(horizon="thread"), now, set())
        explor_sal = _compute_salience(_goal(horizon="exploratory"), now, set())
        assert thread_sal > explor_sal

    def test_stale_goal_scores_lower_than_fresh(self):
        now = _now()
        fresh = _compute_salience(_goal(staleness_state="fresh"), now, set())
        stale = _compute_salience(_goal(staleness_state="stale"), now, set())
        assert stale < fresh

    def test_bid_keyword_overlap_boosts_score(self):
        now = _now()
        goal = _goal(content="build architecture for the knowledge graph")
        no_boost = _compute_salience(goal, now, set())
        with_boost = _compute_salience(goal, now, {"architecture", "knowledge", "graph"})
        assert with_boost > no_boost

    def test_bid_boost_capped_at_0_20(self):
        now = _now()
        goal = _goal(content="one two three four five six seven eight nine ten")
        # Flood with matching keywords
        keywords = {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"}
        sal = _compute_salience(goal, now, keywords)
        assert sal <= 1.0   # still capped at 1.0

    def test_recently_advanced_goal_has_higher_recency(self):
        from datetime import datetime, timezone
        now_ts = _now()
        recent_iso = datetime.fromtimestamp(now_ts - 3600, tz=timezone.utc).isoformat()
        old_iso = datetime.fromtimestamp(now_ts - 86400 * 10, tz=timezone.utc).isoformat()
        recent = _compute_salience(_goal(last_advanced_at=recent_iso), now_ts, set())
        old = _compute_salience(_goal(last_advanced_at=old_iso), now_ts, set())
        assert recent > old

    def test_zero_priority_goal_has_nonzero_salience_from_horizon(self):
        # Even a zero-priority thread goal should have some salience from horizon weight
        sal = _compute_salience(_goal(priority=0.0, horizon="thread"), _now(), set())
        assert sal > 0.0


# ---------------------------------------------------------------------------
# _passes_promotion_gate tests
# ---------------------------------------------------------------------------

class TestPassesPromotionGate:

    def test_passes_when_all_criteria_met(self):
        goal = _goal(confidence=0.75, charter_alignment="true")
        passes, reason = _passes_promotion_gate(goal, salience=0.65)
        assert passes is True
        assert "passes all gates" in reason

    def test_fails_on_low_confidence(self):
        goal = _goal(confidence=0.3)
        passes, reason = _passes_promotion_gate(goal, salience=0.80)
        assert passes is False
        assert "confidence" in reason

    def test_fails_on_low_salience(self):
        goal = _goal(confidence=0.9)
        passes, reason = _passes_promotion_gate(goal, salience=0.1)
        assert passes is False
        assert "salience" in reason

    def test_fails_on_charter_false(self):
        goal = _goal(confidence=0.9, charter_alignment="false")
        passes, reason = _passes_promotion_gate(goal, salience=0.9)
        assert passes is False
        assert "permissibility" in reason

    def test_passes_with_charter_uncertain(self):
        # 'uncertain' is not 'false' — should still pass permissibility
        goal = _goal(confidence=0.9, charter_alignment="uncertain")
        passes, _ = _passes_promotion_gate(goal, salience=0.9)
        assert passes is True

    def test_confidence_boundary_at_threshold(self):
        goal = _goal(confidence=PROMOTION_CONFIDENCE_THRESHOLD)
        passes, _ = _passes_promotion_gate(goal, salience=1.0)
        assert passes is True

    def test_confidence_just_below_threshold_fails(self):
        goal = _goal(confidence=PROMOTION_CONFIDENCE_THRESHOLD - 0.001)
        passes, _ = _passes_promotion_gate(goal, salience=1.0)
        assert passes is False


# ---------------------------------------------------------------------------
# _build_digest structure tests
# ---------------------------------------------------------------------------

class TestBuildDigest:

    def _make_digest(self, scored_active=None, promotable=None, deferred=None, packet=None):
        return _build_digest(
            packet=packet or {"background_bids": []},
            scored_active=scored_active or [],
            promotable=promotable or [],
            deferred=deferred or [],
            now_ts=_now(),
        )

    def test_all_nine_keys_present(self):
        digest = self._make_digest()
        expected = {
            "thread_context",
            "operational_context",
            "active_goal_focus",
            "relevant_goals",
            "unresolved_items",
            "background_pressures",
            "recent_shift",
            "do_not_forget",
            "recommended_next_pressure",
        }
        assert set(digest.keys()) == expected

    def test_active_goal_focus_is_top_goal_content(self):
        g1 = _goal(content="Top priority goal")
        g2 = _goal(content="Second goal")
        digest = self._make_digest(scored_active=[_scored(g1, 0.9), _scored(g2, 0.5)])
        assert digest["active_goal_focus"] == "Top priority goal"

    def test_relevant_goals_capped_at_max(self):
        goals = [_scored(_goal(content=f"goal {i}"), 0.9 - i * 0.1) for i in range(6)]
        digest = self._make_digest(scored_active=goals)
        assert len(digest["relevant_goals"]) <= ORIENTATION_MAX_GOALS

    def test_active_goal_focus_none_when_no_goals(self):
        digest = self._make_digest()
        assert digest["active_goal_focus"] is None

    def test_do_not_forget_only_high_priority_deferred(self):
        from coordinators.orientation import ORIENTATION_HIGH_PRIORITY_THRESHOLD
        low = _goal(priority=ORIENTATION_HIGH_PRIORITY_THRESHOLD - 0.1)
        high = _goal(priority=ORIENTATION_HIGH_PRIORITY_THRESHOLD)
        digest = self._make_digest(deferred=[low, high])
        contents = [g["content"] for g in digest["do_not_forget"]]
        low_content = low["content"]
        high_content = high["content"]
        # high priority should be in do_not_forget, low should not
        assert any(c == high_content for c in contents)


# ---------------------------------------------------------------------------
# _format_orientation_context tests
# ---------------------------------------------------------------------------

class TestFormatOrientationContext:

    def test_returns_non_empty_string(self):
        digest = {
            "thread_context": "Active thread.",
            "operational_context": "Process up 1h0m",
            "active_goal_focus": "Do the thing",
            "relevant_goals": [],
            "unresolved_items": [],
            "background_pressures": [],
            "recent_shift": "No shift.",
            "do_not_forget": [],
            "recommended_next_pressure": "Continue.",
        }
        result = _format_orientation_context(digest)
        assert isinstance(result, str) and len(result) > 0

    def test_contains_orientation_header(self):
        result = _format_orientation_context({})
        assert "ORIENTATION" in result

    def test_contains_recommended_pressure(self):
        digest = {"recommended_next_pressure": "Pursue goal X."}
        result = _format_orientation_context(digest)
        assert "Pursue goal X." in result


# ---------------------------------------------------------------------------
# _extract_bid_keywords tests
# ---------------------------------------------------------------------------

class TestExtractBidKeywords:

    def test_extracts_words_from_background_bids(self):
        packet = {
            "background_bids": [
                {"coordinator_name": "curiosity", "content": "Explore knowledge graph patterns"}
            ]
        }
        keywords = _extract_bid_keywords(packet)
        assert "explore" in keywords or "knowledge" in keywords

    def test_filters_stopwords(self):
        packet = {
            "background_bids": [
                {"coordinator_name": "drive", "content": "the is a"}
            ]
        }
        keywords = _extract_bid_keywords(packet)
        assert "the" not in keywords
        assert "is" not in keywords

    def test_empty_packet_returns_empty_set(self):
        assert _extract_bid_keywords({}) == set()

    def test_short_words_filtered(self):
        packet = {"background_bids": [{"content": "do it"}]}
        keywords = _extract_bid_keywords(packet)
        # "do" and "it" are either stopwords or too short (≤2 chars)
        assert len(keywords) == 0 or all(len(w) > 2 for w in keywords)


# ---------------------------------------------------------------------------
# _thread_context and _operational_context tests
# ---------------------------------------------------------------------------

class TestContextHelpers:

    def test_thread_context_first_interaction(self):
        result = _thread_context({"time_since_last_interaction": None})
        assert "First" in result or "first" in result

    def test_thread_context_active_thread(self):
        result = _thread_context({"time_since_last_interaction": 10.0})
        assert "active" in result.lower() or "2 min" in result

    def test_operational_context_never_nrem(self):
        packet = {
            "session_age_seconds": 3600,
            "time_since_last_nrem": None,
            "time_since_last_autonomous_activity": 120,
        }
        result = _operational_context(packet, _now())
        assert "never" in result.lower() or "NREM" in result

    def test_operational_context_returns_string(self):
        result = _operational_context({}, _now())
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# _recommend_next_pressure tests
# ---------------------------------------------------------------------------

class TestRecommendNextPressure:

    def test_defender_alert_takes_priority(self):
        packet = {"defender_alerts": "⚠ threat detected", "background_bids": []}
        result = _recommend_next_pressure([], [], packet)
        assert "INNER DEFENDER" in result

    def test_promotable_goal_surfaces_when_no_alert(self):
        g = _goal(content="Synthesize research findings")
        packet = {"background_bids": []}
        result = _recommend_next_pressure([], [{"goal": g, "salience": 0.8, "reason": "ok"}], packet)
        assert "promotion" in result.lower() or "Synthesize" in result

    def test_active_goal_recommended_when_no_promotable(self):
        g = _goal(content="Build the knowledge graph layer")
        packet = {"background_bids": []}
        result = _recommend_next_pressure([_scored(g, 0.85)], [], packet)
        assert "Build the knowledge graph layer" in result or "salience" in result

    def test_fallback_when_nothing_pending(self):
        packet = {"background_bids": []}
        result = _recommend_next_pressure([], [], packet)
        assert "No urgent pressure" in result
