from __future__ import annotations

import pytest


def _episode(**overrides):
    from world_models.graph import _episode_properties

    base = {
        "episode_type": "reasoning",
        "content": "Internal deliberation.",
        "session_id": "sess1",
        "environment": "global",
        "coordinator": "mirror_self",
    }
    base.update(overrides)
    return _episode_properties(**base)


def test_episode_properties_prediction_fields_present():
    props = _episode(
        predicted_topic="task 67",
        actual_topic="mirror self",
        prediction_accuracy=0.5,
    )

    assert props["predicted_topic"] == "task 67"
    assert props["actual_topic"] == "mirror self"
    assert props["prediction_accuracy"] == 0.5


def test_episode_properties_prediction_fields_default_none():
    props = _episode()

    assert props["predicted_topic"] is None
    assert props["actual_topic"] is None
    assert props["prediction_accuracy"] is None


def test_episode_properties_valid_curation_label():
    props = _episode(curation_label="keep")

    assert props["curation_label"] == "keep"


def test_episode_properties_invalid_curation_label():
    with pytest.raises(ValueError, match="curation_label"):
        _episode(curation_label="wrong")


def test_episode_properties_curation_label_none_allowed():
    props = _episode(curation_label=None)

    assert props["curation_label"] is None


def test_episode_properties_turn_id():
    props = _episode(turn_id="abc123")

    assert props["turn_id"] == "abc123"


def test_episode_properties_turn_id_none_default():
    props = _episode()

    assert props["turn_id"] is None


def test_curate_episode_invalid_curation_label():
    from world_models.graph import curate_episode

    with pytest.raises(ValueError, match="curation_label"):
        curate_episode(
            object(),
            episode_id="ep1",
            environment="global",
            curation_label="wrong",
        )


def test_curate_episode_returns_false_when_no_updates():
    from world_models.graph import curate_episode

    assert curate_episode(object(), episode_id="ep1", environment="global") is False


def test_curate_episode_updates_fields_with_fake_driver():
    from world_models.graph import curate_episode

    captured = []

    class FakeResult:
        def single(self):
            return {"matched": 1}

    class FakeTx:
        def run(self, cypher, **kwargs):
            captured.append(kwargs)
            return FakeResult()

    class FakeSession:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def execute_write(self, fn):
            return fn(FakeTx())

    class FakeDriver:
        def session(self, **kwargs): return FakeSession()

    result = curate_episode(
        FakeDriver(),
        episode_id="ep1",
        environment="global",
        score=0.8,
        curation_label="review",
    )

    assert result is True
    assert captured[0]["updates"] == {"score": 0.8, "curation_label": "review"}
