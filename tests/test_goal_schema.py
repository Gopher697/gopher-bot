"""
tests/test_goal_schema.py

Non-graph validation tests for the Goal node substrate (Task 62).
No Neo4j connection required — tests _validate_goal_fields() and
the transition state machine logic.
"""
from __future__ import annotations

import pytest

from world_models.graph import (
    _validate_goal_fields,
    _GOAL_STATUS_TRANSITIONS,
    VALID_GOAL_STATUSES,
    VALID_GOAL_HORIZONS,
    VALID_GOAL_AUTHORITY_SCOPES,
    VALID_GOAL_VISIBILITIES,
    VALID_GOAL_DISCLOSURE_TRIGGERS,
    VALID_GOAL_ACTION_BOUNDARIES,
    VALID_GOAL_RISK_LEVELS,
    VALID_GOAL_CHARTER_ALIGNMENTS,
    VALID_GOAL_LIFECYCLE_ANCHORS,
    VALID_GOAL_SOURCES,
    DEFAULT_MAX_CANDIDATE_AGE_SECONDS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_fields(**overrides) -> dict:
    """Return a complete, valid fields dict, optionally overriding keys."""
    base = {
        "status": "candidate",
        "horizon": "thread",
        "authority_scope": "curiosity_exploration",
        "visibility": "private_internal",
        "action_boundary": "reason_only",
        "risk_level": "low",
        "charter_alignment": "true",
        "lifecycle_anchor": "success_condition",
        "source": "self_generated",
        "success_condition": "Understand the user's current project goal.",
        "disclosure_trigger": None,
        "confidence": 0.7,
        "priority": 0.5,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Test 1-9: enum validation — one bad value per field
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field,bad_value", [
    ("status",            "unknown"),
    ("horizon",           "session"),        # 'session' was deliberately removed
    ("authority_scope",   "do_anything"),
    ("visibility",        "hidden"),
    ("action_boundary",   "block"),
    ("risk_level",        "critical"),
    ("charter_alignment", "yes"),
    ("lifecycle_anchor",  "never"),
    ("source",            "magic"),
])
def test_invalid_enum_fields(field, bad_value):
    fields = _valid_fields(**{field: bad_value})
    with pytest.raises(ValueError, match=field):
        _validate_goal_fields(fields)


# ---------------------------------------------------------------------------
# Test 10: valid baseline passes without error
# ---------------------------------------------------------------------------

def test_valid_baseline_passes():
    _validate_goal_fields(_valid_fields())  # must not raise


# ---------------------------------------------------------------------------
# Test 11: requires_disclosure without trigger raises
# ---------------------------------------------------------------------------

def test_disclosure_trigger_required_when_requires_disclosure():
    fields = _valid_fields(
        visibility="requires_disclosure",
        disclosure_trigger=None,
    )
    with pytest.raises(ValueError, match="disclosure_trigger"):
        _validate_goal_fields(fields)


# ---------------------------------------------------------------------------
# Test 12: requires_disclosure with valid trigger passes
# ---------------------------------------------------------------------------

def test_disclosure_trigger_with_requires_disclosure_passes():
    fields = _valid_fields(
        visibility="requires_disclosure",
        disclosure_trigger="on_recommendation",
    )
    _validate_goal_fields(fields)  # must not raise


# ---------------------------------------------------------------------------
# Test 13: disclosure_trigger set without requires_disclosure raises
# ---------------------------------------------------------------------------

def test_disclosure_trigger_without_requires_disclosure_raises():
    fields = _valid_fields(
        visibility="user_visible",
        disclosure_trigger="on_recommendation",
    )
    with pytest.raises(ValueError, match="disclosure_trigger"):
        _validate_goal_fields(fields)


# ---------------------------------------------------------------------------
# Test 14: empty success_condition raises for non-exploratory horizon
# ---------------------------------------------------------------------------

def test_empty_success_condition_raises_for_non_exploratory():
    for horizon in ("thread", "project", "standing"):
        fields = _valid_fields(horizon=horizon, success_condition="")
        with pytest.raises(ValueError, match="success_condition"):
            _validate_goal_fields(fields)


# ---------------------------------------------------------------------------
# Test 15: exploratory horizon allows empty success_condition
# ---------------------------------------------------------------------------

def test_exploratory_allows_empty_success_condition():
    fields = _valid_fields(horizon="exploratory", success_condition="")
    _validate_goal_fields(fields)  # must not raise


# ---------------------------------------------------------------------------
# Test 16: confidence out of range raises
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("val", [-0.01, 1.01, 2.0, -1.0])
def test_confidence_out_of_range(val):
    fields = _valid_fields(confidence=val)
    with pytest.raises(ValueError, match="confidence"):
        _validate_goal_fields(fields)


# ---------------------------------------------------------------------------
# Test 17: priority out of range raises
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("val", [-0.01, 1.01])
def test_priority_out_of_range(val):
    fields = _valid_fields(priority=val)
    with pytest.raises(ValueError, match="priority"):
        _validate_goal_fields(fields)


# ---------------------------------------------------------------------------
# Test 18: terminal statuses have no outgoing transitions
# ---------------------------------------------------------------------------

def test_terminal_statuses_have_no_transitions():
    for terminal in ("completed", "abandoned", "rejected"):
        assert _GOAL_STATUS_TRANSITIONS[terminal] == set(), (
            f"Terminal status {terminal!r} should have no outgoing transitions"
        )


# ---------------------------------------------------------------------------
# Test 19: candidate may transition to active, rejected, or abandoned only
# ---------------------------------------------------------------------------

def test_candidate_transitions():
    allowed = _GOAL_STATUS_TRANSITIONS["candidate"]
    assert allowed == {"active", "rejected", "abandoned"}


# ---------------------------------------------------------------------------
# Test 20: active may transition to completed, abandoned, deferred, dormant
# ---------------------------------------------------------------------------

def test_active_transitions():
    allowed = _GOAL_STATUS_TRANSITIONS["active"]
    assert allowed == {"completed", "abandoned", "deferred", "dormant"}


# ---------------------------------------------------------------------------
# Test 21: DEFAULT_MAX_CANDIDATE_AGE_SECONDS is 7 days
# ---------------------------------------------------------------------------

def test_default_max_candidate_age_is_seven_days():
    assert DEFAULT_MAX_CANDIDATE_AGE_SECONDS == 7 * 24 * 3600


# ---------------------------------------------------------------------------
# Test 22: 'session' is not a valid horizon (persistent AI correction)
# ---------------------------------------------------------------------------

def test_session_not_a_valid_horizon():
    assert "session" not in VALID_GOAL_HORIZONS


# ---------------------------------------------------------------------------
# Test 23: all four horizons are present
# ---------------------------------------------------------------------------

def test_all_four_horizons_present():
    assert VALID_GOAL_HORIZONS == {
        "thread", "project", "standing", "exploratory"
    }
