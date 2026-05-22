"""
Non-graph unit tests for Dream Phase 2 NREM scheduling and TRIAGE/CONSOLIDATE.
No Neo4j connection required.
"""

from __future__ import annotations

import pytest

from coordinators.dream import (
    HEBBIAN_VARIANCE_DECAY,
    HEBBIAN_WEIGHT_DELTA,
    NREM_MIN_INTERVAL_SECONDS,
    NREM_OVERDUE_SECONDS,
    Dream,
    NREMResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_dream(
    time_fn=None,
    sleep_window_fn=None,
    driver_fn=None,
    nrem_done_fn=None,
) -> Dream:
    return Dream(
        driver_fn=driver_fn or (lambda: None),
        nrem_done_fn=nrem_done_fn,
        sleep_window_fn=sleep_window_fn or (lambda: False),
        time_fn=time_fn or (lambda: 1_000_000.0),
    )


# ---------------------------------------------------------------------------
# NREMResult dataclass
# ---------------------------------------------------------------------------

def test_nrem_result_defaults():
    result = NREMResult(ran=True)
    assert result.ran is True
    assert result.skip_reason == ""
    assert result.observations_triaged == 0
    assert result.edges_strengthened == 0
    assert isinstance(result.timestamp, str)


def test_nrem_result_skip():
    result = NREMResult(ran=False, skip_reason="too_soon (120s since last NREM)")
    assert result.ran is False
    assert "too_soon" in result.skip_reason


# ---------------------------------------------------------------------------
# Scheduling: never-run case
# ---------------------------------------------------------------------------

def test_nrem_runs_when_never_run():
    """NREM runs immediately if it has never run before."""
    dream = make_dream()
    result = dream.maybe_run_nrem()
    assert result.ran is True


def test_nrem_sets_last_nrem_unix_after_run():
    fake_time = [1_000_000.0]
    dream = make_dream(time_fn=lambda: fake_time[0])
    dream.maybe_run_nrem()
    assert dream._last_nrem_unix == pytest.approx(1_000_000.0)


# ---------------------------------------------------------------------------
# Scheduling: too-soon suppression
# ---------------------------------------------------------------------------

def test_nrem_skips_when_too_soon():
    """NREM skips if less than NREM_MIN_INTERVAL_SECONDS have elapsed."""
    fake_time = [1_000_000.0]
    dream = make_dream(time_fn=lambda: fake_time[0])
    dream._last_nrem_unix = fake_time[0] - 100.0   # only 100s ago
    result = dream.maybe_run_nrem()
    assert result.ran is False
    assert "too_soon" in result.skip_reason


# ---------------------------------------------------------------------------
# Scheduling: sleep window
# ---------------------------------------------------------------------------

def test_nrem_runs_in_sleep_window():
    """NREM runs when sleep window is active and enough time has passed."""
    base = 1_000_000.0
    dream = make_dream(
        time_fn=lambda: base,
        sleep_window_fn=lambda: True,
    )
    dream._last_nrem_unix = base - NREM_MIN_INTERVAL_SECONDS - 1
    result = dream.maybe_run_nrem()
    assert result.ran is True


def test_nrem_skips_outside_sleep_window_when_not_overdue():
    """NREM skips outside sleep window if not overdue."""
    base = 1_000_000.0
    dream = make_dream(
        time_fn=lambda: base,
        sleep_window_fn=lambda: False,
    )
    # Enough time has passed but not overdue and not in sleep window.
    dream._last_nrem_unix = base - NREM_MIN_INTERVAL_SECONDS - 1
    result = dream.maybe_run_nrem()
    assert result.ran is False
    assert result.skip_reason == "outside_sleep_window"


def test_nrem_runs_when_overdue_outside_sleep_window():
    """NREM runs even outside sleep window when overdue."""
    base = 1_000_000.0
    dream = make_dream(
        time_fn=lambda: base,
        sleep_window_fn=lambda: False,
    )
    dream._last_nrem_unix = base - NREM_OVERDUE_SECONDS - 1
    result = dream.maybe_run_nrem()
    assert result.ran is True


# ---------------------------------------------------------------------------
# nrem_done_fn callback
# ---------------------------------------------------------------------------

def test_nrem_done_fn_called_after_run():
    """nrem_done_fn is called with the unix timestamp when NREM completes."""
    called_with = []
    dream = make_dream(
        time_fn=lambda: 5_000_000.0,
        nrem_done_fn=lambda ts: called_with.append(ts),
    )
    dream.maybe_run_nrem()
    assert len(called_with) == 1
    assert called_with[0] == pytest.approx(5_000_000.0)


def test_nrem_done_fn_not_called_when_skipped():
    """nrem_done_fn is NOT called when NREM is skipped."""
    called_with = []
    dream = make_dream(
        nrem_done_fn=lambda ts: called_with.append(ts),
    )
    dream._last_nrem_unix = 999_999.0   # recent enough to suppress
    result = dream.maybe_run_nrem()
    assert result.ran is False
    assert called_with == []


# ---------------------------------------------------------------------------
# TRIAGE phase (no-graph path)
# ---------------------------------------------------------------------------

def test_triage_returns_empty_when_no_driver():
    """_triage returns [] when driver is None (no graph connection)."""
    dream = make_dream(driver_fn=lambda: None)
    result = dream._triage(None)
    assert result == []


def test_triage_filters_low_confidence():
    """_triage excludes observations below TRIAGE_MIN_CONFIDENCE."""
    from types import SimpleNamespace

    observations = [
        {"content": "A", "confidence": 0.9, "status": "active"},
        {"content": "B", "confidence": 0.1, "status": "active"},   # below threshold
        {"content": "C", "confidence": 0.5, "status": "active"},
    ]

    fake_graph = SimpleNamespace(
        get_recent_observations=lambda driver, environment, hours: observations
    )

    dream = Dream(
        driver_fn=lambda: object(),
        sleep_window_fn=lambda: False,
    )
    # Use a sentinel driver — _triage won't be None-guarded
    candidates = dream._triage(object(), graph_module=fake_graph)
    assert len(candidates) == 2
    contents = [c["content"] for c in candidates]
    assert "A" in contents
    assert "C" in contents
    assert "B" not in contents


# ---------------------------------------------------------------------------
# CONSOLIDATE phase (no-graph path)
# ---------------------------------------------------------------------------

def test_consolidate_returns_zero_with_no_driver():
    dream = make_dream()
    result = dream._consolidate(None, [{"content": "x"}])
    assert result == 0


def test_consolidate_returns_zero_with_empty_candidates():
    dream = make_dream()
    result = dream._consolidate(object(), [])
    assert result == 0


# ---------------------------------------------------------------------------
# _strengthen_edge with fake driver
# ---------------------------------------------------------------------------

def test_strengthen_edge_applies_hebbian_update():
    """_strengthen_edge increases weight and decreases variance."""
    from world_models.graph import MIN_CONSOLIDATION_VARIANCE

    strengthened_calls = []

    class FakeTx:
        def run(self, cypher, **kwargs):
            return FakeResult()

    class FakeResult:
        def single(self):
            return {"weight": 0.6, "consolidation_variance": 0.5}

    class FakeSession:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def execute_read(self, fn):
            return fn(FakeTx())
        def execute_write(self, fn):
            strengthened_calls.append(True)
            return fn(FakeTx())

    class FakeDriver:
        def session(self, **kwargs): return FakeSession()

    from types import SimpleNamespace

    fake_graph = SimpleNamespace(
        get_edge_synaptic_weights=lambda *a, **k: {
            "weight": 0.6,
            "consolidation_variance": 0.5,
        },
        update_edge_synaptic_weights=lambda driver, from_name, rel_type,
            to_name, environment, new_weight, new_variance: (
            strengthened_calls.append({
                "new_weight": new_weight,
                "new_variance": new_variance,
            }) or True
        ),
        MIN_CONSOLIDATION_VARIANCE=MIN_CONSOLIDATION_VARIANCE,
    )

    dream = Dream(environment="global")
    result = dream._strengthen_edge(
        FakeDriver(), "Alice", "RELATED_TO", "Bob", graph_module=fake_graph
    )
    assert result == 1
    assert len(strengthened_calls) == 1
    call = strengthened_calls[0]
    assert call["new_weight"] == pytest.approx(0.6 + HEBBIAN_WEIGHT_DELTA)
    assert call["new_variance"] == pytest.approx(0.5 * HEBBIAN_VARIANCE_DECAY)


def test_strengthen_edge_returns_zero_when_edge_not_found():
    """_strengthen_edge returns 0 when the edge does not exist."""
    from types import SimpleNamespace

    fake_graph = SimpleNamespace(
        get_edge_synaptic_weights=lambda *a, **k: None,  # edge not found
        update_edge_synaptic_weights=lambda *a, **k: False,
        MIN_CONSOLIDATION_VARIANCE=0.01,
    )

    dream = Dream(environment="global")
    result = dream._strengthen_edge(
        object(), "X", "RELATED_TO", "Y", graph_module=fake_graph
    )
    assert result == 0


# ---------------------------------------------------------------------------
# Existing Phase 1 behaviour preserved
# ---------------------------------------------------------------------------

def test_intake_still_works():
    dream = Dream()
    item = dream.intake("what if we tried something new")
    assert "idea" in item.tags


def test_process_still_returns_dream_log_size():
    dream = Dream()
    dream.intake("fragment")
    result = dream.process({})
    assert result["dream_log_size"] == 1
