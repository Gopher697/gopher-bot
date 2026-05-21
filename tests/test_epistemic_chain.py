from __future__ import annotations

import pytest

from world_models.graph import (
    VALID_BELIEF_STATUSES,
    VALID_CLAIM_STATUSES,
    VALID_LEARNING_EPISODE_TYPES,
    VALID_SOURCE_TYPES_EPISTEMIC,
    _belief_properties,
    _claim_properties,
    _doctrine_properties,
    _learning_episode_properties,
    _principle_properties,
    _source_properties,
)


def test_source_type_valid():
    for source_type in VALID_SOURCE_TYPES_EPISTEMIC:
        props = _source_properties("Title", source_type, "global")
        assert props["source_type"] == source_type


def test_source_type_invalid():
    with pytest.raises(ValueError, match="source_type"):
        _source_properties("Title", "rumor", "global")


def test_claim_status_valid():
    for status in VALID_CLAIM_STATUSES:
        props = _claim_properties("claim", "source1", "global", "memory", status=status)
        assert props["status"] == status


def test_claim_status_invalid():
    with pytest.raises(ValueError, match="status"):
        _claim_properties("claim", "source1", "global", "memory", status="bad")


def test_belief_status_invalid():
    with pytest.raises(ValueError, match="status"):
        _belief_properties("belief", "global", status="bad")


def test_principle_scope_invalid():
    with pytest.raises(ValueError, match="scope"):
        _principle_properties("principle", "global", "bad")


def test_principle_status_invalid():
    with pytest.raises(ValueError, match="status"):
        _principle_properties("principle", "global", "values", status="bad")


def test_doctrine_status_invalid():
    with pytest.raises(ValueError, match="status"):
        _doctrine_properties("doctrine", "global", status="bad")


def test_learning_episode_type_invalid():
    with pytest.raises(ValueError, match="learning_type"):
        _learning_episode_properties("s1", "global", "memory", "bad")


def test_source_properties_fields():
    props = _source_properties(
        "  Paper Title  ",
        "paper",
        "global",
        url="https://example.com",
        author="  Ada  ",
        summary="  Useful paper.  ",
    )

    assert props["title"] == "Paper Title"
    assert props["source_type"] == "paper"
    assert props["environment"] == "global"
    assert props["url"] == "https://example.com"
    assert props["author"] == "Ada"
    assert props["summary"] == "Useful paper."
    assert props["status"] == "active"
    assert "created_at" in props


def test_claim_properties_confidence_clamped():
    props = _claim_properties("claim", "source1", "global", "memory", confidence=1.5)
    assert props["confidence"] == 1.0


def test_claim_properties_confidence_floor():
    props = _claim_properties("claim", "source1", "global", "memory", confidence=-0.1)
    assert props["confidence"] == 0.0


def test_claim_properties_default_status():
    props = _claim_properties("claim", "source1", "global", "memory")
    assert props["status"] == "candidate"


def test_belief_properties_default_status():
    props = _belief_properties("belief", "global")
    assert props["status"] == "forming"


def test_belief_properties_claim_count_zero():
    props = _belief_properties("belief", "global")
    assert props["claim_count"] == 0


def test_principle_properties_scope_stored():
    props = _principle_properties("principle", "global", "values")
    assert props["scope"] == "values"


def test_doctrine_properties_version_floor():
    props = _doctrine_properties("doctrine", "global", version=0)
    assert props["version"] == 1


def test_doctrine_properties_immutable_false_by_default():
    props = _doctrine_properties("doctrine", "global")
    assert props["immutable"] is False


def test_doctrine_properties_parent_id():
    props = _doctrine_properties(
        "doctrine",
        "global",
        parent_doctrine_id="abc",
    )
    assert props["parent_doctrine_id"] == "abc"


def test_learning_episode_properties_fields():
    props = _learning_episode_properties(
        "sess1",
        "global",
        "memory",
        "ingestion",
        source_id="source1",
        turn_id="turn1",
        summary="  learned something  ",
    )

    assert props["session_id"] == "sess1"
    assert props["environment"] == "global"
    assert props["coordinator"] == "memory"
    assert props["learning_type"] == "ingestion"
    assert props["source_id"] == "source1"
    assert props["turn_id"] == "turn1"
    assert props["summary"] == "learned something"
    assert props["claim_count"] == 0
    assert "created_at" in props


def test_learning_episode_properties_source_id_none_default():
    props = _learning_episode_properties("sess1", "global", "memory", "reflection")
    assert props["source_id"] is None


def test_learning_episode_properties_turn_id_stored():
    props = _learning_episode_properties(
        "sess1",
        "global",
        "memory",
        "conversation",
        turn_id="xyz",
    )
    assert props["turn_id"] == "xyz"


def test_learning_episode_type_valid():
    for learning_type in VALID_LEARNING_EPISODE_TYPES:
        props = _learning_episode_properties("sess1", "global", "memory", learning_type)
        assert props["learning_type"] == learning_type
