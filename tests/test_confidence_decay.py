"""
Tests for P-001 Refinement 2 - confidence decay infrastructure.

  - _observation_properties() includes last_confirmed_at
  - decay_stale_observations() exists and has the expected signature
  - Dream's NREM phase calls decay_stale_observations when a driver is available
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# _observation_properties - last_confirmed_at field
# ---------------------------------------------------------------------------

def test_observation_properties_includes_last_confirmed_at():
    """Every new Observation node must carry last_confirmed_at."""
    from world_models.graph import _observation_properties

    props = _observation_properties(
        content="test observation",
        environment="global",
        coordinator="test",
    )
    assert "last_confirmed_at" in props
    assert props["last_confirmed_at"] is not None


def test_last_confirmed_at_is_iso_string():
    """last_confirmed_at must be an ISO-format string for Neo4j comparison."""
    import re
    from world_models.graph import _observation_properties

    props = _observation_properties("test", "global", "test")
    val = props["last_confirmed_at"]
    assert re.match(r"^\d{4}-\d{2}-\d{2}", str(val))


# ---------------------------------------------------------------------------
# decay_stale_observations - function contract
# ---------------------------------------------------------------------------

def test_decay_stale_observations_is_importable():
    """decay_stale_observations must be importable from world_models.graph."""
    from world_models.graph import decay_stale_observations

    assert callable(decay_stale_observations)


def test_decay_stale_observations_has_expected_signature():
    """decay_stale_observations must accept driver, environment, and options."""
    import inspect
    from world_models.graph import decay_stale_observations

    sig = inspect.signature(decay_stale_observations)
    params = list(sig.parameters.keys())
    assert "driver" in params
    assert "environment" in params
    assert "days_threshold" in params
    assert "decay_factor" in params
    assert "min_confidence" in params


# ---------------------------------------------------------------------------
# Dream NREM wires decay
# ---------------------------------------------------------------------------

def test_dream_nrem_calls_decay_stale_observations(monkeypatch):
    """
    Dream._run_nrem() must call decay_stale_observations on the graph driver
    when a driver is available.
    """
    import coordinators.dream as dream_mod
    from coordinators.dream import Dream

    decay_calls: list[tuple] = []

    mock_graph = MagicMock()
    mock_graph.get_recent_observations.return_value = []
    mock_graph.record_system_event.return_value = None
    mock_graph.close.return_value = None

    def capture_decay(driver, environment, **kwargs):
        decay_calls.append((driver, environment))
        return 0

    mock_graph.decay_stale_observations.side_effect = capture_decay

    original_import = dream_mod.import_module

    def patched_import(name):
        if name == "world_models.graph":
            return mock_graph
        return original_import(name)

    monkeypatch.setattr(dream_mod, "import_module", patched_import)
    monkeypatch.setattr(Dream, "_save_dream_log", lambda self, result: None)

    sentinel_driver = object()
    dream = Dream(
        driver_fn=lambda: sentinel_driver,
        sleep_window_fn=lambda: True,
    )
    dream._last_nrem_unix = 0.0
    dream._run_nrem(time.time())

    assert decay_calls, "decay_stale_observations was not called during NREM"
    assert decay_calls[0][0] is sentinel_driver
    assert decay_calls[0][1] == "global"
