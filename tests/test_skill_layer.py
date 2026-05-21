from __future__ import annotations

import pytest

from world_models.graph import (
    SKILL_EMA_ALPHA,
    VALID_SKILL_DOMAINS,
    VALID_SKILL_STATUSES,
    _skill_properties,
    update_skill_status,
)


class _DriverMustNotBeUsed:
    def session(self, *args, **kwargs):
        raise AssertionError("driver should not be invoked")


def test_domain_valid():
    for domain in VALID_SKILL_DOMAINS:
        props = _skill_properties("mirror_self", "topic_prediction", domain, "global")
        assert props["domain"] == domain


def test_domain_invalid():
    with pytest.raises(ValueError, match="domain"):
        _skill_properties("mirror_self", "topic_prediction", "bad", "global")


def test_status_valid():
    for status in VALID_SKILL_STATUSES:
        props = _skill_properties(
            "mirror_self",
            "topic_prediction",
            "prediction",
            "global",
            status=status,
        )
        assert props["status"] == status


def test_status_invalid():
    with pytest.raises(ValueError, match="status"):
        _skill_properties(
            "mirror_self",
            "topic_prediction",
            "prediction",
            "global",
            status="bad",
        )


def test_update_skill_status_invalid():
    with pytest.raises(ValueError, match="status"):
        update_skill_status(_DriverMustNotBeUsed(), "skill1", "global", "bad")


def test_properties_required_keys():
    props = _skill_properties("memory", "semantic_retrieval", "retrieval", "global")
    required = {
        "coordinator",
        "skill_name",
        "domain",
        "environment",
        "proficiency",
        "status",
        "practice_count",
        "success_count",
        "created_at",
        "last_practiced_at",
    }
    assert required <= set(props.keys())


def test_properties_practice_count_zero():
    props = _skill_properties("memory", "semantic_retrieval", "retrieval", "global")
    assert props["practice_count"] == 0


def test_properties_success_count_zero():
    props = _skill_properties("memory", "semantic_retrieval", "retrieval", "global")
    assert props["success_count"] == 0


def test_properties_last_practiced_none():
    props = _skill_properties("memory", "semantic_retrieval", "retrieval", "global")
    assert props["last_practiced_at"] is None


def test_properties_proficiency_clamped_high():
    props = _skill_properties(
        "memory",
        "semantic_retrieval",
        "retrieval",
        "global",
        initial_proficiency=2.0,
    )
    assert props["proficiency"] == 1.0


def test_properties_proficiency_clamped_low():
    props = _skill_properties(
        "memory",
        "semantic_retrieval",
        "retrieval",
        "global",
        initial_proficiency=-0.5,
    )
    assert props["proficiency"] == 0.0


def test_properties_default_status_active():
    props = _skill_properties("memory", "semantic_retrieval", "retrieval", "global")
    assert props["status"] == "active"


def test_properties_domain_stored():
    props = _skill_properties(
        "mirror_self",
        "topic_prediction",
        "prediction",
        "global",
    )
    assert props["domain"] == "prediction"


def test_properties_coordinator_stripped():
    props = _skill_properties(
        "  mirror_self  ",
        "topic_prediction",
        "prediction",
        "global",
    )
    assert props["coordinator"] == "mirror_self"


def test_skill_ema_alpha_range():
    assert 0.0 < SKILL_EMA_ALPHA < 1.0
