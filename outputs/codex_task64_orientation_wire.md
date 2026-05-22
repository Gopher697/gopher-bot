# Codex Task 64 — Wire Orientation into Awareness + Update Registry

## Context

Orientation coordinator was built in Task 63 (`coordinators/orientation.py`). It builds a situation digest — active goals, deferred items, background pressure, recommended next focus — and injects it into the packet as `packet["orientation"]` and `packet["orientation_context"]`.

Right now Orientation exists but nothing calls it. This task wires it into the Awareness foreground pipeline so Reason sees the orientation digest on every turn.

**Correct pipeline position:** After `_drain_bids_into_packet()` (Orientation needs `packet["background_bids"]` for salience scoring) and before `reason.process()` (Reason needs `packet["orientation_context"]`).

This task also updates `docs/COORDINATOR_REGISTRY.md` to:
1. Add Orientation's entry (it is built and active — the registry doesn't know it exists)
2. Fix Dream's stale status (says "Phase 2 pending as Task 47" — Task 47 is shipped)

---

## Files to modify

- `coordinators/awareness.py` — add Orientation to `__init__` and `synchronous_run()`
- `docs/COORDINATOR_REGISTRY.md` — add Orientation entry, fix Dream entry

## Files to create

- `tests/test_awareness_orientation.py` — pipeline integration tests (no Neo4j required)

Do not modify any other file.

---

## Part 1 — Modify `coordinators/awareness.py`

### 1a. Add import at the top of the file

After the existing coordinator imports (near the `from coordinators.voice import Voice` line), add:

```python
from coordinators.orientation import Orientation
```

This is a runtime import, not TYPE_CHECKING — Orientation is instantiated at init time.

### 1b. Add `orientation` parameter to `__init__`

Current signature ends with:
```python
    hands: "Hands | None" = None,
```

Add after `hands`:
```python
    orientation: Orientation | Coordinator | None = None,
```

### 1c. Add `self.orientation` assignment in `__init__` body

After the `self.hands = hands` line, add:
```python
        self.orientation = orientation or Orientation()
```

`Orientation()` defaults to `environment="global"`. If Neo4j is unavailable, `Orientation.process()` catches the exception internally and returns an empty orientation dict — no error propagates.

### 1d. Wire Orientation into `synchronous_run()`

Find this block in `synchronous_run()`:

```python
            self._drain_bids_into_packet(packet)

            packet = self.reason.process(packet)
```

Replace it with:

```python
            self._drain_bids_into_packet(packet)

            # --- Orientation: situation awareness digest ----------------------
            # Runs after bid drain (needs background_bids for salience scoring)
            # and before Reason (injects orientation_context into memory_context).
            try:
                packet = self.orientation.process(packet)
                orientation_ctx = str(packet.get("orientation_context") or "").strip()
                if orientation_ctx:
                    memory_context = str(packet.get("memory_context") or "").strip()
                    packet["memory_context"] = (
                        f"{memory_context}\n\n{orientation_ctx}"
                        if memory_context
                        else orientation_ctx
                    )
            except Exception:
                pass  # Orientation failure is non-fatal — pipeline continues
            # -----------------------------------------------------------------

            packet = self.reason.process(packet)
```

That is the complete change to `awareness.py`. The orientation digest is now visible to Reason on every turn via `memory_context`, and also available in raw structured form at `packet["orientation"]` for any coordinator that wants it.

---

## Part 2 — Update `docs/COORDINATOR_REGISTRY.md`

### 2a. Fix Dream's stale status entry

Find the Dream entry's Status row:

```
| Status | Active — Phase 1 scaffold built (coordinators/dream.py); intake + TRIAGE stub; Phase 2 deep build (graph integration + CONSOLIDATE/AUDIT) pending as Task 47 |
```

Replace with:

```
| Status | Active — Phase 2 complete (Tasks 47a, 47b, 60): TRIAGE (confidence ≥ 0.4), CONSOLIDATE (Hebbian weight strengthening, variance decay), AUDIT (hash chain verify + injection scan), DreamLog (JSON to logs/dream/), OpenTimestamps anchoring (23h gate, a.pool.opentimestamps.org). NREM scheduling: circadian gate (NREM_MIN_INTERVAL=6h, NREM_OVERDUE=26h). NE spike on chain failure: PRIORITY_SAFETY bid to Awareness (Inner Defender layer 1 of 3). nrem_done_fn callback updates Awareness.last_nrem_time after each NREM pass. |
```

### 2b. Add Orientation entry

Insert the following entry as a new `###` section in the **Active Coordinators** list. Place it after the Awareness entry (Orientation runs inside Awareness's pipeline, so it belongs near it in the registry).

```markdown
---

### Orientation

| Field | Value |
|---|---|
| Status | Active — built (coordinators/orientation.py); wired into Awareness.synchronous_run() after bid drain and before Reason; injecting orientation digest on every foreground turn (Task 64) |
| Model tier | Tier 0 — pure Python; no LLM calls; deterministic salience arithmetic and graph reads only |
| Backing context | Runtime-only |
| Backing agent | None — fully deterministic |
| Neuroscience analogue | Entorhinal cortex + hippocampal–prefrontal interface — situation modeling, temporal context integration, projection of current state into near-future relevance |
| Layer | Cognitive (foreground pipeline, pre-Reason) |
| Primary role | Build a situation digest each turn: active goal focus, relevant goals ranked by salience, deferred items, background coordinator pressure, recommended next action |
| Read access | Neo4j Goal nodes (active, candidate, deferred); packet temporal fields (time_since_last_interaction, time_since_last_nrem, session_age_seconds); packet background_bids (for bid-pressure salience boost) |
| Write paths | Goal promotion only: candidate→active when three-score gate passes (confidence ≥ 0.60, salience ≥ 0.50, charter_alignment ≠ false). Writes promotion audit trail to the Goal node. No other durable writes. |
| Packet fields written | `packet["orientation"]` — full digest dict (9 fields); `packet["orientation_context"]` — plain-text digest for Reason; `packet["promotable_goal_ids"]` — goal_ids promoted this turn |
| Three-score gate | **Confidence** (epistemic: is this a real goal?) ≥ 0.60 AND **Salience** (computed: does this matter now?) ≥ 0.50 AND **Permissibility** (charter_alignment ≠ 'false'). Salience factors: priority (0.40) + horizon weight (0.35) + recency of last_advanced_at (0.25) + bid keyword overlap boost (up to +0.20). |
| Behavioral rules | Orientation does not generate content or make decisions — it builds context that Reason uses to make better decisions. It auto-promotes goals autonomously when the three-score gate passes — this is the AI's own evaluation, not a user-approval step. It never blocks the pipeline: all graph failures are swallowed and result in an empty orientation dict. The orientation digest is compact enough to stay within Reason's context budget; it surfaces at most 3 relevant goals, 3 deferred items, and 3 background pressures per turn. |
| Relationship to Awareness | Orientation is a foreground coordinator instantiated by Awareness and called inside `synchronous_run()`. It is not a background coordinator and has no `background_tick()`. It does not submit bids to the bid queue. |
| Notes | Orientation is Endsley Level 3: from where we are, where might this go? Without it, Reason knows what was said (Sensory), what is remembered (Memory), and what the background coordinators are signalling (bid_context) — but not what the AI is actively pursuing or what it should attend to next. Orientation supplies that missing layer. |
```

---

## Part 3 — Create `tests/test_awareness_orientation.py`

No Neo4j required. Tests verify that Orientation is wired correctly and that pipeline failures are handled gracefully.

```python
"""
tests/test_awareness_orientation.py

Integration tests for Orientation wiring inside Awareness.synchronous_run().
No Neo4j connection required — uses mock coordinators.
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
    """Always raises — simulates graph unavailability."""
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
    """Minimal Awareness with noop coordinators, no external calls."""
    return Awareness(
        sensory=_NoopCoordinator(),
        memory=memory or _NoopCoordinator(),
        reason=_NoopCoordinator(),
        voice=_NoopCoordinator(),
        orientation=orientation or _MockOrientation(),
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
# Test 4: Orientation failure does NOT propagate — pipeline completes
# ---------------------------------------------------------------------------

def test_orientation_failure_is_non_fatal():
    aw = _make_awareness(orientation=_RaisingOrientation())
    # Must not raise — pipeline continues with orientation absent
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
    # Orientation context alone is sufficient — no crash
    assert "ORIENTATION" in mem_ctx
```

---

## Commit instructions

Run both test suites:
```
pytest tests/test_awareness_orientation.py --basetemp .tmp/pytest_codex_task64 -v
pytest tests/test_orientation.py --basetemp .tmp/pytest_codex_task63 -v
pytest tests/test_goal_schema.py --basetemp .tmp/pytest_codex_task62 -v
```

All must pass. Then:
```
git add coordinators/awareness.py docs/COORDINATOR_REGISTRY.md tests/test_awareness_orientation.py
git commit -m "feat: wire Orientation into Awareness pipeline; update COORDINATOR_REGISTRY (Task 64)"
```

**Do not stage world_models/config.py.** Verify with `git status` before committing.

---

## Summary of changes

| File | Change |
|---|---|
| `coordinators/awareness.py` | Import Orientation; add `orientation` parameter to `__init__`; `self.orientation = orientation or Orientation()`; wire `orientation.process(packet)` + context merge between bid drain and Reason |
| `docs/COORDINATOR_REGISTRY.md` | Fix Dream status (Phase 2 complete, not pending); add full Orientation entry |
| `tests/test_awareness_orientation.py` | 8 pipeline integration tests; mock coordinators only; no Neo4j |

After this commit, the full foreground pipeline is:

```
Sensory → Memory → [bid drain] → Orientation → Reason → [Hands] → Voice → [Feeling.observe]
```

Orientation is the last major foreground coordinator to wire in. Task 65 (education arc) and Task 66 (behavioral update mechanism) are post-live, blocked by trust escalation (Task 49).
