# Codex Task 67 — Mirror-Self as Generative Model: Prediction Fields + Foreground Wiring

## Context

Mirror-Self is currently a self-affect/confidence tracker running only in the background
loop. For gopher-bot to function as a prediction machine (predictive processing framework),
Mirror-Self must become the generative model — the component that holds world-state
expectations, measures prediction error, and surfaces when its model is consistently wrong.

Key insight: predictions originate from the AI's own self-model (Mirror-Self), not from
the user model (Mirror-User). Mirror-User contributes data; Mirror-Self generates the
prediction.

Two things to build:
1. Add prediction fields and logic to `coordinators/mirror_self.py`
2. Wire `MirrorSelf` into `Awareness.synchronous_run` (foreground pipeline) — after Keeper,
   before Reason — so prediction comparison and formation happen every turn.

Also fix: `_submit_mirror_self_bid` still has an old getattr/.put_nowait fallback that
violates the codebase contract. Simplify to `awareness_queue.submit(bid)` directly.

---

## Security invariant — check before every commit

`world_models/config.py` is gitignored and contains Neo4j credentials and API keys.
Run `git status` before committing. If `world_models/config.py` appears, STOP — do not commit.

---

## Part 1: New constants in `coordinators/mirror_self.py`

Add after existing constants:

```python
# Prediction machine — generative model constants.
PREDICTION_EMA_ALPHA = 0.3          # weight for newest accuracy sample vs. history
PREDICTION_LOW_ACCURACY_THRESHOLD = 0.20   # EMA below this = world-model is struggling
PREDICTION_LOW_ACCURACY_STREAK_LIMIT = 3   # consecutive low-accuracy turns before bid
PREDICTION_STOP_WORDS = frozenset({
    "the", "a", "an", "is", "in", "on", "at", "to", "for", "of",
    "and", "or", "but", "with", "i", "you", "we", "it", "this", "that",
    "do", "can", "will", "just", "so", "what", "how", "why",
})
```

---

## Part 2: New fields in `SelfState` dataclass

Add to `SelfState`:

```python
# Generative model — prediction tracking.
predicted_topic: str = ""                  # what Mirror-Self expects next turn to address
last_prediction_accuracy: float = 0.0     # Jaccard similarity score for most recent turn
prediction_accuracy_ema: float = 0.5      # exponential moving average of accuracy
low_accuracy_streak: int = 0              # consecutive turns below PREDICTION_LOW_ACCURACY_THRESHOLD
```

---

## Part 3: New module-level helper — `_jaccard_similarity`

```python
def _jaccard_similarity(a: str, b: str) -> float:
    """
    Word-level Jaccard similarity between two strings, after stop-word removal.
    Returns 0.0 if either string is empty after filtering.
    """
    words_a = {w for w in a.lower().split() if w not in PREDICTION_STOP_WORDS}
    words_b = {w for w in b.lower().split() if w not in PREDICTION_STOP_WORDS}
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)
```

---

## Part 4: Update `MirrorSelf.process(packet) -> dict`

The foreground pipeline now calls `process()` every turn. The method does two things in
sequence:

**Step 1 — measure last prediction against actual message:**

```python
message = str(packet.get("message") or "").strip()
if message and self.state.predicted_topic:
    accuracy = _jaccard_similarity(self.state.predicted_topic, message)
    self.state.last_prediction_accuracy = accuracy
    # Update EMA
    self.state.prediction_accuracy_ema = (
        PREDICTION_EMA_ALPHA * accuracy
        + (1 - PREDICTION_EMA_ALPHA) * self.state.prediction_accuracy_ema
    )
    # Track low-accuracy streak
    if self.state.prediction_accuracy_ema < PREDICTION_LOW_ACCURACY_THRESHOLD:
        self.state.low_accuracy_streak += 1
    else:
        self.state.low_accuracy_streak = 0
```

**Step 2 — form new prediction for next turn from orientation context:**

Read `packet.get("orientation", {})`. The `orientation` dict (produced by Orientation
coordinator) contains `active_goal_focus` as its primary signal. Use this as the
predicted topic for next turn.

```python
orientation = packet.get("orientation") or {}
active_goal = str(orientation.get("active_goal_focus") or "").strip()
recommended = str(orientation.get("recommended_next_pressure") or "").strip()
# Prefer active_goal_focus; fall back to recommended_next_pressure; fall back to ""
self.state.predicted_topic = active_goal or recommended or ""
```

**Step 3 — existing logic (unchanged):** error tracking, confidence adjustment, disk
fields, self-affect recomputation.

**Step 4 — extend `packet["mirror_self_state"]`:**

Add the new fields:
```python
packet["mirror_self_state"] = {
    ...existing fields...,
    "predicted_topic": self.state.predicted_topic,
    "last_prediction_accuracy": round(self.state.last_prediction_accuracy, 4),
    "prediction_accuracy_ema": round(self.state.prediction_accuracy_ema, 4),
    "low_accuracy_streak": self.state.low_accuracy_streak,
}
```

---

## Part 5: Update `_build_observation` to surface low-accuracy signal

In `_build_observation`, add a check for persistent low accuracy:

```python
if state.low_accuracy_streak >= PREDICTION_LOW_ACCURACY_STREAK_LIMIT:
    return (
        f"World-model accuracy degraded — EMA={state.prediction_accuracy_ema:.0%} "
        f"for {state.low_accuracy_streak} consecutive turns. "
        "Generative model may need recalibration."
    )
```

This should be checked before the confidence check (it's a higher-priority signal).

---

## Part 6: Update `_snapshot` and `_restore_state`

Add prediction fields to `_snapshot()`:
```python
"predicted_topic": self.state.predicted_topic,
"last_prediction_accuracy": self.state.last_prediction_accuracy,
"prediction_accuracy_ema": self.state.prediction_accuracy_ema,
"low_accuracy_streak": self.state.low_accuracy_streak,
```

Add to `_restore_state()`:
```python
predicted_topic = snapshot.get("predicted_topic")
if isinstance(predicted_topic, str):
    self.state.predicted_topic = predicted_topic

prediction_accuracy_ema = snapshot.get("prediction_accuracy_ema")
if isinstance(prediction_accuracy_ema, float):
    self.state.prediction_accuracy_ema = max(0.0, min(1.0, prediction_accuracy_ema))

low_accuracy_streak = snapshot.get("low_accuracy_streak")
if isinstance(low_accuracy_streak, int):
    self.state.low_accuracy_streak = max(0, low_accuracy_streak)
```

---

## Part 7: Fix `_submit_mirror_self_bid` dead code

Replace the current getattr dance with the codebase-contract-compliant form:

```python
def _submit_mirror_self_bid(awareness_queue, observation: str) -> None:
    import time as _time
    bid = MirrorSelfBid(
        coordinator_name="mirror_self",
        content=observation,
        timestamp=_time.time(),
    )
    awareness_queue.submit(bid)
```

---

## Part 8: Wire MirrorSelf into `coordinators/awareness.py`

### Import
```python
from coordinators.mirror_self import MirrorSelf
```

### `Awareness.__init__` — add `mirror_self` parameter

```python
def __init__(
    self,
    ...,
    mirror_self: MirrorSelf | Coordinator | None = None,
) -> None:
    ...
    self.mirror_self = mirror_self or MirrorSelf()
```

### `synchronous_run` — insert after Keeper block, before Reason

```python
# --- Mirror-Self: generative model — prediction comparison + new prediction ---
# Runs after Keeper (reads trust_level) and after Orientation (reads active_goal_focus).
# Compares last turn's prediction against actual message; forms new prediction.
try:
    packet = self.mirror_self.process(packet)
except Exception:
    pass  # Mirror-Self failure is non-fatal — pipeline continues
# -----------------------------------------------------------------------------
```

The pipeline position is: Orientation → Keeper → **Mirror-Self** → Reason.

---

## Part 9: Tests — `tests/test_mirror_self.py`

Add new tests (do not remove existing ones):

**Jaccard similarity:**
- `test_jaccard_identical_strings` — same text → 1.0
- `test_jaccard_no_overlap` — completely different words → 0.0
- `test_jaccard_partial_overlap` — some shared words → value between 0 and 1
- `test_jaccard_stop_words_filtered` — strings that only share stop words → 0.0
- `test_jaccard_empty_after_filter` — both strings are only stop words → 0.0

**Prediction accuracy tracking:**
- `test_prediction_accuracy_computed_when_message_and_prediction_present` — set
  `state.predicted_topic = "task 67 mirror self"`, call `process` with
  `message = "working on task 67"`; assert `state.last_prediction_accuracy > 0`
- `test_prediction_accuracy_zero_when_no_prior_prediction` — `predicted_topic = ""`; 
  call `process` with any message; assert `last_prediction_accuracy == 0.0` (no
  comparison made when no prior prediction)
- `test_ema_updated_after_turn` — after `process` with matching message, assert
  `prediction_accuracy_ema` has moved from 0.5 toward 1.0
- `test_low_accuracy_streak_increments` — force EMA below threshold (call process
  multiple times with non-matching messages); assert `low_accuracy_streak` increases

**New prediction formed:**
- `test_new_prediction_from_orientation_active_goal` — pass packet with
  `orientation = {"active_goal_focus": "write the keeper coordinator"}`; after
  `process`, assert `state.predicted_topic == "write the keeper coordinator"`
- `test_new_prediction_falls_back_to_recommended` — `active_goal_focus = ""`,
  `recommended_next_pressure = "check audit log"` → `predicted_topic == "check audit log"`
- `test_new_prediction_empty_when_no_orientation` — no `orientation` key → `predicted_topic == ""`

**Low-accuracy bid:**
- `test_low_accuracy_observation_emitted_after_streak` — set
  `state.low_accuracy_streak = PREDICTION_LOW_ACCURACY_STREAK_LIMIT`,
  `state.prediction_accuracy_ema = 0.1`; call `_build_observation`; assert result
  contains "World-model accuracy degraded"

**Snapshot / restore:**
- `test_predicted_topic_persisted_and_restored` — set `state.predicted_topic = "test topic"`;
  snapshot = `_snapshot()`; new state via `_restore_state(snapshot)`; assert
  `state.predicted_topic == "test topic"`

**`_submit_mirror_self_bid` — no more getattr:**
- `test_submit_bid_calls_submit_directly` — pass a mock with a `.submit()` recorder;
  assert `.submit()` was called once with a `MirrorSelfBid`; assert no `.put_nowait()`
  call was attempted

---

## Verification

```
pytest tests/test_mirror_self.py --basetemp .tmp/pytest_codex_task67 -v
pytest tests/test_awareness_orientation.py --basetemp .tmp/pytest_codex_task67 -v
pytest --ignore=tests/test_graph.py --basetemp .tmp/pytest_codex_task67 -v
```

Confirm `world_models/config.py` is NOT staged:
```
git status
```

Commit:
```
git commit -m "feat: Mirror-Self generative model — prediction tracking + foreground pipeline wiring (Task 67)"
```

---

## Summary of changes

| File | Change |
|---|---|
| `coordinators/mirror_self.py` | New constants: `PREDICTION_EMA_ALPHA`, `PREDICTION_LOW_ACCURACY_THRESHOLD`, `PREDICTION_LOW_ACCURACY_STREAK_LIMIT`, `PREDICTION_STOP_WORDS` |
| `coordinators/mirror_self.py` | `SelfState`: add `predicted_topic`, `last_prediction_accuracy`, `prediction_accuracy_ema`, `low_accuracy_streak` |
| `coordinators/mirror_self.py` | New helper: `_jaccard_similarity` |
| `coordinators/mirror_self.py` | `process()`: Step 1 measure accuracy, Step 2 form new prediction, Step 4 extend packet field |
| `coordinators/mirror_self.py` | `_build_observation`: add low-accuracy streak check (highest priority signal) |
| `coordinators/mirror_self.py` | `_snapshot` / `_restore_state`: persist and restore prediction fields |
| `coordinators/mirror_self.py` | `_submit_mirror_self_bid`: remove getattr dance, call `.submit()` directly |
| `coordinators/awareness.py` | Add `mirror_self` to `__init__`; wire into `synchronous_run` after Keeper, before Reason |
| `tests/test_mirror_self.py` | ~14 new tests |
