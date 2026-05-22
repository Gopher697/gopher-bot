# Codex Task 48 — Idle Cultivation Loop: Monitoring Foundation

## Context

Gopher-bot runs a persistent BrainLoop alongside the Flask server. Currently, it only
acts when Gopher sends a message. Task 48 builds the *detection and monitoring* foundation
for autonomous idle-time operation:

1. **Drive: disk footprint self-awareness** — `shutil.disk_usage()` monitoring with thresholds
2. **Drive: idle state detection** — detects when Gopher has been away and signals cultivation mode
3. **Mirror-Self: physical footprint field** — adds disk usage to the AI's self-model
4. **Cultivation bid** — Drive emits a structured bid when idle + disk status is notable

The actual autonomous action loop (Curiosity→Hands→Dream execution cycle) is blocked by
Task 49 (trust escalation protocol). Task 48 builds what T49 needs: a reliable idle
signal and disk-aware resource monitoring.

---

## Security invariant — check before every commit

`world_models/config.py` is gitignored and contains Neo4j credentials and API keys.
Run `git status` before committing. If `world_models/config.py` appears, STOP — do not commit.

---

## Part 1: Drive — disk footprint monitoring + idle detection

**File:** `coordinators/drive.py`

### New constants (add after existing constants)

```python
# Idle cultivation — Gopher absence threshold before Drive signals cultivation mode.
IDLE_THRESHOLD_SECONDS = 1800           # 30 minutes

# Disk footprint thresholds (bytes).
DISK_WARNING_FRACTION = 0.80            # 80% disk used → warning
DISK_CRITICAL_FRACTION = 0.95           # 95% disk used → critical

# Drive cadence for cultivation checks (separate from daily commitment check).
CULTIVATION_CADENCE_SECONDS = 900       # check every 15 minutes when idle
```

### `DriveState` dataclass — new fields

Add to the `DriveState` dataclass:

```python
# Disk footprint (populated by background_tick via _disk_usage_fn).
disk_total_bytes: int = 0
disk_used_bytes: int = 0
disk_free_bytes: int = 0

# Idle cultivation.
idle_since_seconds: float | None = None   # time_since_last_interaction when idle first detected
last_cultivation_tick: float = 0.0        # unix timestamp of last cultivation bid
```

### `Drive.__init__` — new injectable

Add `disk_usage_fn` parameter (injectable for tests, defaults to `shutil.disk_usage`):

```python
def __init__(
    self,
    commitments_reader: CommitmentsReader | None = None,
    clock: Clock | None = None,
    budget_ceiling: float = DEFAULT_BUDGET_CEILING,
    disk_usage_fn: Callable[[], tuple[int, int, int]] | None = None,
) -> None:
    self.commitments_reader = commitments_reader or _default_commitments_reader
    self.clock = clock or (lambda: datetime.now(UTC))
    self.state = DriveState(budget_ceiling=budget_ceiling)
    self.disk_usage_fn = disk_usage_fn or _default_disk_usage
```

`_default_disk_usage` (module-level function):
```python
def _default_disk_usage() -> tuple[int, int, int]:
    import shutil
    usage = shutil.disk_usage(".")
    return usage.total, usage.used, usage.free
```

Returns `(total_bytes, used_bytes, free_bytes)`. On any OSError, returns `(0, 0, 0)`.

### `Drive.process` — read idle signal from packet

In `process(self, packet: dict) -> dict`, after the existing model_tier handling, read the
idle state from the packet's temporal data:

```python
time_since_last = packet.get("time_since_last_interaction", 0)
if isinstance(time_since_last, (int, float)) and time_since_last > IDLE_THRESHOLD_SECONDS:
    if self.state.idle_since_seconds is None:
        self.state.idle_since_seconds = float(time_since_last)
else:
    self.state.idle_since_seconds = None
```

Extend `packet["drive_budget_status"]` to include disk and idle fields:

```python
packet["drive_budget_status"] = {
    "session_budget_used": round(self.state.session_budget_used, 4),
    "budget_ceiling": self.state.budget_ceiling,
    "budget_fraction": round(_budget_fraction(self.state), 4),
    "api_calls_by_tier": dict(self.state.session_api_calls),
    "disk_total_bytes": self.state.disk_total_bytes,
    "disk_used_bytes": self.state.disk_used_bytes,
    "disk_free_bytes": self.state.disk_free_bytes,
    "disk_fraction": _disk_fraction(self.state),
    "idle_since_seconds": self.state.idle_since_seconds,
}
```

### `Drive.background_tick` — disk check + cultivation bid

In `background_tick(self, awareness_queue) -> None`, after the commitment check, add:

1. **Update disk stats:**
```python
try:
    total, used, free = self.disk_usage_fn()
    self.state.disk_total_bytes = total
    self.state.disk_used_bytes = used
    self.state.disk_free_bytes = free
except Exception:
    pass
```

2. **Check if cultivation bid should fire:**
The existing logic only submits if `observation != last_bid_content`. Keep that, but add
a cultivation signal to the observation when idle:

```python
cultivation_note = _build_cultivation_note(self.state, now)
```

Merge `cultivation_note` into the observation string if it's non-empty. The cultivation
note should only fire when:
- `self.state.idle_since_seconds` is not None (Drive knows we're idle via packet)
- Enough time has passed since last cultivation tick

```python
def _build_cultivation_note(state: DriveState, now: datetime) -> str:
    import time as _time
    if state.idle_since_seconds is None:
        return ""
    elapsed_since_last = _time.time() - state.last_cultivation_tick
    if elapsed_since_last < CULTIVATION_CADENCE_SECONDS:
        return ""
    idle_minutes = int(state.idle_since_seconds // 60)
    disk_pct = _disk_fraction(state)
    disk_status = (
        "critical" if disk_pct >= DISK_CRITICAL_FRACTION
        else "warning" if disk_pct >= DISK_WARNING_FRACTION
        else "ok"
    )
    used_gb = state.disk_used_bytes / 1_073_741_824
    free_gb = state.disk_free_bytes / 1_073_741_824
    return (
        f"[cultivation mode] idle {idle_minutes}m; "
        f"disk {used_gb:.1f}GB used / {free_gb:.1f}GB free (status={disk_status})"
    )
```

When a cultivation note fires, update `state.last_cultivation_tick = time.time()`.

### Helper functions

```python
def _disk_fraction(state: DriveState) -> float:
    if state.disk_total_bytes == 0:
        return 0.0
    return round(state.disk_used_bytes / state.disk_total_bytes, 4)
```

---

## Part 2: Mirror-Self — physical footprint field

**File:** `coordinators/mirror_self.py`

### `SelfState` dataclass — new fields

```python
disk_used_bytes: int = 0
disk_free_bytes: int = 0
```

### `MirrorSelf.process` — read disk data from Drive's packet field

In `process(self, packet: dict) -> dict`, after reading `curiosity_gaps`, also read
disk data that Drive has already placed in `packet["drive_budget_status"]`:

```python
drive_status = packet.get("drive_budget_status", {})
disk_used = drive_status.get("disk_used_bytes", 0)
disk_free = drive_status.get("disk_free_bytes", 0)
if isinstance(disk_used, int) and disk_used > 0:
    self.state.disk_used_bytes = disk_used
if isinstance(disk_free, int) and disk_free > 0:
    self.state.disk_free_bytes = disk_free
```

**Pipeline ordering note:** Drive runs before Mirror-Self in the foreground pipeline
(Drive.process → ... → Mirror-Self.process). In the pipeline defined in
`coordinators/awareness.py` (or wherever `process` ordering is set), confirm Drive
precedes Mirror-Self. If not, do not fix the ordering in this task — instead just
add a comment noting the dependency.

### Extend `packet["mirror_self_state"]`

Add disk fields to the dict returned in `process`:

```python
packet["mirror_self_state"] = {
    "self_affect": self.state.self_affect,
    "confidence_map": dict(self.state.confidence_map),
    "open_gaps_proxy": self.state.open_gaps_proxy,
    "session_interaction_count": self.state.session_interaction_count,
    "disk_used_bytes": self.state.disk_used_bytes,
    "disk_free_bytes": self.state.disk_free_bytes,
}
```

### `_snapshot` — persist disk fields

Add to `_snapshot()`:
```python
"disk_used_bytes": self.state.disk_used_bytes,
"disk_free_bytes": self.state.disk_free_bytes,
```

### `_restore_state` — restore disk fields

Add to `_restore_state()`:
```python
disk_used = snapshot.get("disk_used_bytes")
if isinstance(disk_used, int):
    self.state.disk_used_bytes = max(0, disk_used)
disk_free = snapshot.get("disk_free_bytes")
if isinstance(disk_free, int):
    self.state.disk_free_bytes = max(0, disk_free)
```

### Self-affect update — disk pressure

In `_derive_self_affect`, add a disk pressure check. If disk is in critical range
(>95% full), return `SELF_AFFECT_FRUSTRATED` (or add a new `SELF_AFFECT_PRESSURED`
constant). Use the existing affect derivation order — disk pressure should rank
between `error_run >= 3` and the confidence check. Choose whichever constant fits
best without adding unnecessary new constants.

---

## Part 3: Tests

### `tests/test_drive.py` — add new tests

All tests pure Python, no network, no real disk I/O.

**Disk monitoring:**
- `test_background_tick_updates_disk_stats` — inject `disk_usage_fn` returning `(1000, 800, 200)`;
  after `background_tick`, assert `state.disk_total_bytes == 1000`, `state.disk_used_bytes == 800`
- `test_disk_fraction_zero_when_total_zero` — assert `_disk_fraction(state)` returns `0.0` when
  `disk_total_bytes == 0`
- `test_drive_budget_status_includes_disk_fields` — call `process(packet)` after a background_tick
  that set disk stats; assert `packet["drive_budget_status"]` contains `disk_total_bytes`,
  `disk_used_bytes`, `disk_free_bytes`, `disk_fraction`, `idle_since_seconds`

**Idle detection:**
- `test_idle_detected_when_time_exceeds_threshold` — call `process` with packet containing
  `time_since_last_interaction = IDLE_THRESHOLD_SECONDS + 1`; assert `state.idle_since_seconds`
  is not None
- `test_idle_cleared_when_interaction_resumes` — set `state.idle_since_seconds` to a value,
  then call `process` with `time_since_last_interaction = 10`; assert `state.idle_since_seconds is None`

**Cultivation bid:**
- `test_cultivation_note_fires_when_idle` — set `state.idle_since_seconds = 2000.0` and
  `state.last_cultivation_tick = 0.0`; assert `_build_cultivation_note(state, now)` is non-empty
- `test_cultivation_note_suppressed_within_cadence` — set `state.last_cultivation_tick` to
  `time.time() - 60` (recent); assert `_build_cultivation_note` returns `""`
- `test_cultivation_note_absent_when_not_idle` — `state.idle_since_seconds = None`;
  assert `_build_cultivation_note` returns `""`

### `tests/test_mirror_self.py` — add new tests

- `test_disk_fields_read_from_packet` — call `process` with packet containing
  `drive_budget_status = {"disk_used_bytes": 500, "disk_free_bytes": 100}`;
  assert `state.disk_used_bytes == 500`, `state.disk_free_bytes == 100`
- `test_disk_fields_in_mirror_self_state_packet` — same setup; assert
  `packet["mirror_self_state"]["disk_used_bytes"] == 500`
- `test_disk_fields_persisted_in_snapshot` — set `state.disk_used_bytes = 999`;
  call `_snapshot()`; assert `"disk_used_bytes"` in snapshot with value 999
- `test_disk_fields_restored_from_snapshot` — call `_restore_state({"disk_used_bytes": 888,
  "disk_free_bytes": 111})`; assert `state.disk_used_bytes == 888`

---

## Verification

```
pytest tests/test_drive.py --basetemp .tmp/pytest_codex_task48 -v
pytest tests/test_mirror_self.py --basetemp .tmp/pytest_codex_task48 -v
pytest --ignore=tests/test_graph.py --basetemp .tmp/pytest_codex_task48 -v
```

Confirm `world_models/config.py` is NOT staged:
```
git status
```

Commit:
```
git commit -m "feat: idle cultivation monitoring — disk footprint + idle detection in Drive/Mirror-Self (Task 48)"
```

---

## Summary of changes

| File | Change |
|---|---|
| `coordinators/drive.py` | New constants: `IDLE_THRESHOLD_SECONDS`, `DISK_WARNING_FRACTION`, `DISK_CRITICAL_FRACTION`, `CULTIVATION_CADENCE_SECONDS` |
| `coordinators/drive.py` | `DriveState`: add `disk_total_bytes`, `disk_used_bytes`, `disk_free_bytes`, `idle_since_seconds`, `last_cultivation_tick` |
| `coordinators/drive.py` | `Drive.__init__`: add injectable `disk_usage_fn` |
| `coordinators/drive.py` | `Drive.process`: read idle state from `time_since_last_interaction`; extend `drive_budget_status` packet field |
| `coordinators/drive.py` | `Drive.background_tick`: update disk stats; add cultivation note to observation |
| `coordinators/drive.py` | New helpers: `_default_disk_usage`, `_disk_fraction`, `_build_cultivation_note` |
| `coordinators/mirror_self.py` | `SelfState`: add `disk_used_bytes`, `disk_free_bytes` |
| `coordinators/mirror_self.py` | `MirrorSelf.process`: read disk from `drive_budget_status`; extend `mirror_self_state` packet field |
| `coordinators/mirror_self.py` | `_snapshot` / `_restore_state`: persist and restore disk fields |
| `coordinators/mirror_self.py` | `_derive_self_affect`: add disk pressure check |
| `tests/test_drive.py` | ~8 new tests for disk monitoring, idle detection, cultivation bid |
| `tests/test_mirror_self.py` | ~4 new tests for disk fields |
