# Codex Tasks 54 + 55 — Training Corpus Foundation: Turn Audit Log + Episode Prediction Fields

## Context

Mirror-Self (Task 67) now tracks prediction accuracy every foreground turn: `predicted_topic`,
`last_prediction_accuracy`, `prediction_accuracy_ema`, `low_accuracy_streak`. This data is
currently only in the live packet and Mirror-Self's in-memory state — it is never written to
disk in a way that can be used for training corpus construction or self-model retrospection.

Two things to build:
1. **Turn audit log** (`logs/audit/turns.jsonl`) — a flat per-turn record capturing prediction
   state, trust level, orientation goal, tier, and cost. Written from `Awareness.synchronous_run`
   at the end of every foreground turn.
2. **Episode node enrichment** (`world_models/graph.py`) — add prediction fields
   (`predicted_topic`, `actual_topic`, `prediction_accuracy`, `curation_label`, `turn_id`) to
   `_episode_properties`, `add_episode`, `add_utterance`, and the `Memory` coordinator wrappers.
   Also add a `curate_episode` function for post-hoc training corpus labeling.

---

## Security invariant — check before every commit

`world_models/config.py` is gitignored and contains Neo4j credentials and API keys.
Run `git status` before committing. If `world_models/config.py` appears, STOP — do not commit.

---

## Part 1: Turn audit log — `coordinators/base.py`

### New constant

```python
TURN_LOG_PATH = PROJECT_ROOT / "logs" / "audit" / "turns.jsonl"
```

### `build_turn_log_entry(packet: dict) -> dict[str, Any]`

Module-level function. Reads from the packet and builds a structured turn record.
All fields have safe defaults — this must never raise.

```python
def build_turn_log_entry(packet: dict) -> dict[str, Any]:
    """
    Build a per-turn audit record from a completed foreground pipeline packet.

    Should be called after Voice.process() so all pipeline fields are present.
    Returns a plain dict suitable for JSON serialization.
    """
    import time as _time

    mirror = packet.get("mirror_self_state") or {}
    orientation = packet.get("orientation") or {}

    return {
        "turn_id": str(packet.get("turn_id") or ""),
        "session_id": str(packet.get("session_id") or ""),
        "timestamp": float(packet.get("_turn_ts") or _time.time()),
        "trust_level": int(packet.get("trust_level") or 0),
        "tier": packet.get("tier"),
        "predicted_topic": str(mirror.get("predicted_topic") or ""),
        "last_prediction_accuracy": float(mirror.get("last_prediction_accuracy") or 0.0),
        "prediction_accuracy_ema": float(mirror.get("prediction_accuracy_ema") or 0.5),
        "low_accuracy_streak": int(mirror.get("low_accuracy_streak") or 0),
        "self_affect": str(mirror.get("self_affect") or "stable"),
        "orientation_active_goal": str(orientation.get("active_goal_focus") or ""),
        "has_error": bool(packet.get("error")),
        "bid_count": int(len(packet.get("background_bids") or [])),
        "actual_cost_usd": float(packet.get("actual_cost_usd") or 0.0),
    }
```

### `append_turn_log_entry(entry: dict[str, Any], path: Path = TURN_LOG_PATH) -> None`

```python
def append_turn_log_entry(
    entry: dict[str, Any],
    path: Path = TURN_LOG_PATH,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
```

### `read_turn_log_entries(limit: int = 50, path: Path = TURN_LOG_PATH) -> list[dict[str, Any]]`

Same pattern as `read_coordinator_log_entries` — read last `limit` lines, parse JSON,
skip blank/malformed lines, return list of dicts.

---

## Part 2: Wire turn log into `coordinators/awareness.py`

### Import additions

```python
from coordinators.base import (
    Coordinator,
    append_coordinator_log_entry,
    backfill_coordinator_log_acceptance,
    build_coordinator_log_entry,
    build_turn_log_entry,
    append_turn_log_entry,
)
```

### `synchronous_run` — generate `turn_id` at the top

Add immediately after `packet["session_id"] = self.session_id`:

```python
import time as _turn_time
packet["turn_id"] = _uuid.uuid4().hex
packet["_turn_ts"] = _turn_time.time()
```

### `synchronous_run` — write turn log at the end

Add in the `try` block, after `self.voice.process(packet)` and before `return packet`:

```python
# --- Turn audit log ------------------------------------------
# Captures per-turn prediction state, trust, cost for training corpus.
# Must run after Voice (all pipeline fields present). Non-fatal.
try:
    turn_entry = build_turn_log_entry(packet)
    append_turn_log_entry(turn_entry)
except Exception:
    pass
# -------------------------------------------------------------
```

---

## Part 3: Episode node enrichment — `world_models/graph.py`

### New valid set

```python
VALID_CURATION_LABELS = {"keep", "skip", "review"}
```

### Update `_episode_properties` signature

Add new keyword-only parameters after `score`:

```python
def _episode_properties(
    episode_type: str,
    content: str,
    session_id: str,
    environment: str,
    coordinator: str,
    source_type: str = "observed",
    *,
    tts_generated: bool = False,
    accepted: bool = False,
    score: float | None = None,
    # Training corpus fields (T54/T55)
    predicted_topic: str | None = None,
    actual_topic: str | None = None,
    prediction_accuracy: float | None = None,
    curation_label: str | None = None,
    turn_id: str | None = None,
) -> Dict[str, Any]:
```

Add validation for `curation_label`:

```python
if curation_label is not None and curation_label not in VALID_CURATION_LABELS:
    raise ValueError(
        f"curation_label must be one of {sorted(VALID_CURATION_LABELS)!r} or None, "
        f"got {curation_label!r}"
    )
```

Add new fields to the `props` dict:

```python
# Training corpus fields — populated at write time from Mirror-Self state.
"predicted_topic": predicted_topic,
"actual_topic": actual_topic,
"prediction_accuracy": prediction_accuracy,
"curation_label": curation_label,
"turn_id": str(turn_id) if turn_id is not None else None,
```

### Update `add_episode` signature

Thread the five new fields through identically to how `score` is handled — accept as kwargs,
pass to `_episode_properties`.

```python
def add_episode(
    driver,
    episode_type: str,
    content: str,
    session_id: str,
    environment: str,
    coordinator: str,
    source_type: str = "observed",
    tts_generated: bool = False,
    accepted: bool = False,
    score: float | None = None,
    predicted_topic: str | None = None,
    actual_topic: str | None = None,
    prediction_accuracy: float | None = None,
    curation_label: str | None = None,
    turn_id: str | None = None,
) -> str:
```

### Update `add_utterance`

Add `turn_id`, `predicted_topic`, `actual_topic`, `prediction_accuracy`, `curation_label`
parameters (all `None` by default). Pass through to `add_episode`.

```python
def add_utterance(
    driver,
    content: str,
    session_id: str,
    environment: str,
    tts_generated: bool = False,
    predicted_topic: str | None = None,
    actual_topic: str | None = None,
    prediction_accuracy: float | None = None,
    curation_label: str | None = None,
    turn_id: str | None = None,
) -> str:
```

### New function: `curate_episode`

```python
def curate_episode(
    driver,
    episode_id: str,
    environment: str,
    *,
    score: float | None = None,
    curation_label: str | None = None,
) -> bool:
    """
    Update the training curation fields on an existing Episode node.

    Called post-hoc when a human or automated process labels an episode
    for inclusion in or exclusion from the training corpus.

    Args:
        driver:         Active Neo4j driver.
        episode_id:     The episode_id of the target node.
        environment:    Graph environment scope (used to scope the match).
        score:          Optional float (0.0–1.0) quality score.
        curation_label: One of VALID_CURATION_LABELS or None (leave unchanged).

    Returns:
        True if a node was matched and updated, False if not found.
    """
    if curation_label is not None and curation_label not in VALID_CURATION_LABELS:
        raise ValueError(
            f"curation_label must be one of {sorted(VALID_CURATION_LABELS)!r} or None"
        )

    updates: dict[str, Any] = {}
    if score is not None:
        updates["score"] = float(score)
    if curation_label is not None:
        updates["curation_label"] = curation_label

    if not updates:
        return False  # nothing to do

    def write(tx):
        result = tx.run(
            """
            MATCH (e:Episode {episode_id: $episode_id, environment: $environment})
            SET e += $updates
            RETURN count(e) AS matched
            """,
            episode_id=episode_id,
            environment=environment,
            updates=updates,
        )
        record = result.single()
        return bool(record and record["matched"] > 0)

    with _session(driver) as session:
        return session.execute_write(write)
```

---

## Part 4: Update `Memory` coordinator — `coordinators/memory.py`

### `record_utterance` — add new params

```python
def record_utterance(
    self,
    content: str,
    session_id: str,
    environment: str = "global",
    tts_generated: bool = False,
    predicted_topic: str | None = None,
    actual_topic: str | None = None,
    prediction_accuracy: float | None = None,
    curation_label: str | None = None,
    turn_id: str | None = None,
) -> str:
```

Pass all new params through to `graph.add_utterance`.

### `record_reasoning` — add `turn_id`

```python
def record_reasoning(
    self,
    content: str,
    session_id: str,
    coordinator: str,
    environment: str = "global",
    accepted: bool = False,
    source_type: str = "observed",
    turn_id: str | None = None,
) -> str:
```

Pass `turn_id` through to `graph.add_episode`.

---

## Part 5: Tests

### `tests/test_turn_log.py` — new file

**Turn log entry builder:**
- `test_build_turn_log_entry_minimal` — packet with only `session_id` and `turn_id` → entry
  has correct session_id, turn_id; prediction fields default to 0.0 / "" / False
- `test_build_turn_log_entry_full_mirror_self_state` — packet with complete `mirror_self_state`
  dict → all prediction fields extracted correctly
- `test_build_turn_log_entry_trust_level` — `packet["trust_level"] = 1` → entry
  `trust_level == 1`
- `test_build_turn_log_entry_has_error_true` — `packet["error"] = "something failed"` →
  `has_error is True`
- `test_build_turn_log_entry_has_error_false` — no error key → `has_error is False`
- `test_build_turn_log_entry_bid_count` — `packet["background_bids"] = [{}, {}, {}]` →
  `bid_count == 3`
- `test_build_turn_log_entry_orientation_goal` — `packet["orientation"] = {"active_goal_focus":
  "write keeper"}` → `orientation_active_goal == "write keeper"`
- `test_build_turn_log_entry_safe_on_empty_packet` — `build_turn_log_entry({})` → no exception,
  all fields have safe defaults

**Append / read round-trip (uses `tmp_path` fixture, injectable path):**
- `test_append_turn_log_creates_file` — call `append_turn_log_entry(entry, tmp_path/…)` →
  file exists with one line
- `test_read_turn_log_empty_file_returns_empty_list` — non-existent path → `[]`
- `test_read_turn_log_round_trip` — append 3 entries, read → list of 3 dicts
- `test_read_turn_log_respects_limit` — append 10, read with `limit=3` → 3 entries (last 3)

### `tests/test_graph.py` (or a new `tests/test_episode_schema.py`) — new tests for `_episode_properties`

To avoid requiring Neo4j, test `_episode_properties` directly (it's pure Python):

- `test_episode_properties_prediction_fields_present` — pass `predicted_topic="task 67"`,
  `actual_topic="mirror self"`, `prediction_accuracy=0.5` → all three keys in returned dict
- `test_episode_properties_prediction_fields_default_none` — no args → `predicted_topic`,
  `actual_topic`, `prediction_accuracy` are all `None`
- `test_episode_properties_valid_curation_label` — `curation_label="keep"` → in props
- `test_episode_properties_invalid_curation_label` — `curation_label="wrong"` → `ValueError`
- `test_episode_properties_curation_label_none_allowed` — `curation_label=None` → no error
- `test_episode_properties_turn_id` — `turn_id="abc123"` → `props["turn_id"] == "abc123"`
- `test_episode_properties_turn_id_none_default` — no arg → `props["turn_id"] is None`

---

## Verification

```
pytest tests/test_turn_log.py --basetemp .tmp/pytest_codex_task5455 -v
pytest tests/test_episode_schema.py --basetemp .tmp/pytest_codex_task5455 -v
pytest --ignore=tests/test_graph.py --basetemp .tmp/pytest_codex_task5455 -v
```

Confirm `world_models/config.py` is NOT staged:
```
git status
```

Commit:
```
git commit -m "feat: turn audit log + Episode prediction fields for training corpus (Tasks 54+55)"
```

---

## Summary of changes

| File | Change |
|---|---|
| `coordinators/base.py` | New constant `TURN_LOG_PATH`; new functions `build_turn_log_entry`, `append_turn_log_entry`, `read_turn_log_entries` |
| `coordinators/awareness.py` | Generate `turn_id` + `_turn_ts` at turn start; write turn log after Voice |
| `world_models/graph.py` | `VALID_CURATION_LABELS`; new fields in `_episode_properties`; update `add_episode` + `add_utterance`; new `curate_episode` function |
| `coordinators/memory.py` | Update `record_utterance` + `record_reasoning` signatures to pass through new fields |
| `tests/test_turn_log.py` | New — ~12 unit tests for turn log functions |
| `tests/test_episode_schema.py` | New — ~7 unit tests for enriched `_episode_properties` |
