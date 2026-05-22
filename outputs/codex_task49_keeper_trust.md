# Codex Task 49 — Keeper Coordinator: Trust Escalation Protocol

## Context

Keeper is the last planned coordinator in the gopher-bot architecture. Its role is charter
enforcement and autonomy trust management. The trust level Keeper produces determines what
gopher-bot is permitted to do when Gopher is not present.

Currently, Drive detects idle state and emits cultivation bids, but nothing acts on them
because the trust level for autonomous action hasn't been established. Keeper provides that
gate.

Two things to build:
1. `coordinators/keeper.py` — the Keeper coordinator
2. Wire Keeper into `coordinators/awareness.py` (after Orientation, before Reason)

---

## Security invariant — check before every commit

`world_models/config.py` is gitignored and contains Neo4j credentials and API keys.
Run `git status` before committing. If `world_models/config.py` appears, STOP — do not commit.

---

## Trust Level Schema

```python
TRUST_LEVEL_REACTIVE   = 0   # Acts only on Gopher input — no autonomous action permitted
TRUST_LEVEL_SUPERVISED = 1   # Local graph writes permitted (curiosity gap logging, autonomous Observation)
TRUST_LEVEL_EXTENDED   = 2   # Reserved: approved read-only external requests (not yet active)
TRUST_LEVEL_AUTONOMOUS = 3   # Reserved: approved external writes with full audit (not yet active)
```

For this task, implement levels 0 and 1 only. Levels 2 and 3 are defined as constants but
no logic gates on them yet — they are placeholders for future escalation steps.

---

## Part 1: `coordinators/keeper.py`

### Constants

```python
KEEPER_CADENCE_SECONDS = 300        # background_tick runs every 5 minutes
KEEPER_PRIORITY = 4                 # bid priority — between Mirror-Self (3) and Drive (6)

# Minimum consecutive clean NREM cycles to reach Level 1.
MIN_CLEAN_NREM_STREAK = 3

# DreamLog directory (relative to project root).
DREAM_LOG_DIR = "logs/dream"

# How many recent DreamLog entries to scan when computing streak.
DREAM_LOG_SCAN_LIMIT = 10
```

### `KeeperState` dataclass

```python
@dataclass
class KeeperState:
    trust_level: int = TRUST_LEVEL_REACTIVE
    clean_nrem_streak: int = 0        # consecutive clean NREM audit cycles
    last_demotion_reason: str = ""    # human-readable reason for most recent demotion
    last_elevation_ts: float = 0.0    # unix timestamp of most recent elevation
    last_demoted_ts: float = 0.0      # unix timestamp of most recent demotion
    last_bid_content: str | None = None
```

### `KeeperBid` frozen dataclass

```python
@dataclass(frozen=True)
class KeeperBid:
    coordinator_name: str
    content: str
    priority: int
    timestamp: float
    source: str = "keeper"
    type: str = "trust_level_signal"
```

### `Keeper` class

```python
class Keeper(Coordinator):
    name = "keeper"

    def __init__(
        self,
        dream_log_reader: Callable[[], list[dict]] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        import time as _time
        self.dream_log_reader = dream_log_reader or _default_dream_log_reader
        self.clock = clock or _time.time
        self.state = KeeperState()
```

`_default_dream_log_reader` (module-level) reads JSON files from `DREAM_LOG_DIR`,
sorted by filename (ascending — filenames are `YYYY-MM-DD_HHMMSS.json` so sort order
= time order), returns the last `DREAM_LOG_SCAN_LIMIT` entries as parsed dicts.
On any error (directory absent, malformed JSON), returns `[]`.

```python
def _default_dream_log_reader() -> list[dict]:
    import json
    import pathlib

    log_dir = pathlib.Path(DREAM_LOG_DIR)
    if not log_dir.exists():
        return []
    try:
        files = sorted(log_dir.glob("*.json"))[-DREAM_LOG_SCAN_LIMIT:]
        entries = []
        for f in files:
            try:
                entries.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                continue
        return entries
    except Exception:
        return []
```

### `Keeper.process(packet) -> dict`

Called each foreground turn. Reads evidence from the current packet, updates trust state,
and injects trust context into the packet.

**Evidence read from packet:**

1. `defender_alerts = packet.get("defender_alerts", [])` — if non-empty, immediately demote
2. `time_since_last = packet.get("time_since_last_interaction")` — informational only; not
   a trust gate (trust level is independent of whether Gopher is present)

**Trust demotion on defender alert:**

If `defender_alerts` is a non-empty list:
```python
if defender_alerts and self.state.trust_level > TRUST_LEVEL_REACTIVE:
    self.state.trust_level = TRUST_LEVEL_REACTIVE
    self.state.clean_nrem_streak = 0
    self.state.last_demotion_reason = f"inner defender alert: {defender_alerts[0][:80]}"
    self.state.last_demoted_ts = self.clock()
```

Demotion takes effect immediately — no grace period.

**Trust elevation check:**

Only attempt elevation if currently at Level 0:
```python
if self.state.trust_level == TRUST_LEVEL_REACTIVE:
    if self.state.clean_nrem_streak >= MIN_CLEAN_NREM_STREAK:
        self.state.trust_level = TRUST_LEVEL_SUPERVISED
        self.state.last_elevation_ts = self.clock()
```

**Packet injection:**

```python
packet["trust_level"] = self.state.trust_level
packet["keeper_context"] = _build_keeper_context(self.state)
```

`_build_keeper_context(state)` returns a plain-text one-line summary:
```
"trust_level={N} clean_nrem_streak={N} last_demotion={reason or 'none'}"
```

Append `keeper_context` to `memory_context` (same pattern as orientation_context):
```python
keeper_ctx = packet.get("keeper_context", "").strip()
if keeper_ctx:
    existing = str(packet.get("memory_context", "")).strip()
    packet["memory_context"] = f"{existing}\n\n{keeper_ctx}" if existing else keeper_ctx
```

Return `packet`.

### `Keeper.background_tick(awareness_queue) -> None`

Reads DreamLog files to update `clean_nrem_streak`. Runs on `KEEPER_CADENCE_SECONDS`.

```python
async def background_tick(self, awareness_queue) -> None:
    entries = self.dream_log_reader()
    self.state.clean_nrem_streak = _compute_clean_streak(entries)

    observation = _build_observation(self.state)
    if not observation or observation == self.state.last_bid_content:
        return

    import time as _time
    bid = KeeperBid(
        coordinator_name=self.name,
        content=observation,
        priority=KEEPER_PRIORITY,
        timestamp=_time.time(),
    )
    try:
        awareness_queue.submit(bid)
        self.state.last_bid_content = observation
    except Exception:
        pass
```

`_compute_clean_streak(entries: list[dict]) -> int` (module-level):

Iterate entries from most recent backwards. Count consecutive entries where
`entry.get("audit", {}).get("chain_ok", True) is True`.
Stop counting on the first entry where `chain_ok` is False.
Return the count.

```python
def _compute_clean_streak(entries: list[dict]) -> int:
    streak = 0
    for entry in reversed(entries):
        audit = entry.get("audit", {})
        if audit.get("chain_ok", True) is True:
            streak += 1
        else:
            break
    return streak
```

`_build_observation(state: KeeperState) -> str | None`:
Only emit a bid when the trust level has changed since the last bid, or when there's
a demotion reason to surface:

```python
def _build_observation(state: KeeperState) -> str | None:
    level_name = {
        TRUST_LEVEL_REACTIVE: "reactive",
        TRUST_LEVEL_SUPERVISED: "supervised",
    }.get(state.trust_level, str(state.trust_level))

    if state.trust_level == TRUST_LEVEL_REACTIVE and state.last_demotion_reason:
        return (
            f"Trust level: {level_name} (streak={state.clean_nrem_streak}) "
            f"— demoted: {state.last_demotion_reason}"
        )
    if state.trust_level >= TRUST_LEVEL_SUPERVISED:
        return (
            f"Trust level: {level_name} (streak={state.clean_nrem_streak}) "
            "— local autonomous writes permitted"
        )
    return f"Trust level: {level_name} (streak={state.clean_nrem_streak})"
```

---

## Part 2: Wire Keeper into `coordinators/awareness.py`

### Imports

Add to imports:
```python
from coordinators.keeper import Keeper
```

### `Awareness.__init__` — add `keeper` parameter

```python
def __init__(
    self,
    ...,
    keeper: Keeper | Coordinator | None = None,
) -> None:
    ...
    self.keeper = keeper or Keeper()
```

### `synchronous_run` — insert after Orientation block, before Reason

After the Orientation block (which ends with the `except Exception: pass` catching
orientation failures), add:

```python
# --- Keeper: trust level gate -----------------------------------------------
# Runs after Orientation (reads orientation context) and before Reason
# (injects trust_level so Reason is aware of autonomy constraints).
try:
    packet = self.keeper.process(packet)
    keeper_ctx = str(packet.get("keeper_context") or "").strip()
    if keeper_ctx:
        memory_context = str(packet.get("memory_context") or "").strip()
        packet["memory_context"] = (
            f"{memory_context}\n\n{keeper_ctx}"
            if memory_context
            else keeper_ctx
        )
except Exception:
    pass  # Keeper failure is non-fatal — pipeline continues without trust gate
# ---------------------------------------------------------------------------
```

Note: the `memory_context` merge is handled inside `Keeper.process` already, so the
block above is redundant — only keep the try/except wrapper and the `packet = self.keeper.process(packet)` call. Remove the duplicate memory_context merge from the wiring code (let Keeper.process handle it internally).

### BrainLoop registration

In whatever file registers coordinators with BrainLoop (likely `app.py` or the BrainLoop
setup), add `keeper` to the background coordinator list so `background_tick` is called
on its cadence. Use `KEEPER_CADENCE_SECONDS` as the tick interval.

If the BrainLoop registration pattern is unclear from reading the file, add a TODO comment
marking where Keeper's background tick should be registered rather than guessing.

---

## Part 3: Update `COORDINATOR_REGISTRY.md`

Add Keeper to the registry. Follow the exact format of existing entries.

Key fields:
- **name:** `keeper`
- **role:** Charter enforcement and autonomy trust management. Computes trust level from
  DreamLog streak and inner defender alerts. Injects `trust_level` into packet before
  Reason. Gates autonomous capability expansion.
- **type:** foreground + background
- **foreground position:** after Orientation, before Reason
- **background cadence:** 300s
- **tier:** Tier 0 — no LLM calls, no graph writes, pure Python state machine

---

## Part 4: Tests — `tests/test_keeper.py` (new file)

All pure Python. Injectable `dream_log_reader` and `clock`. No disk I/O, no Neo4j.

**Trust level computation:**

- `test_trust_reactive_by_default` — new Keeper has `trust_level == 0`
- `test_trust_elevates_after_clean_streak` — inject `dream_log_reader` returning 3
  clean entries; call `background_tick`; assert `state.clean_nrem_streak == 3`;
  then call `process({})` and assert `packet["trust_level"] == 1`
- `test_trust_stays_reactive_with_short_streak` — 2 clean entries → streak == 2 → still level 0
- `test_streak_broken_by_chain_failure` — 5 entries, the 4th has `chain_ok: False`;
  assert streak == 1 (only the last entry, after the break)

**Trust demotion:**

- `test_demoted_on_defender_alert` — set `state.trust_level = 1`, call `process` with
  `defender_alerts=["⚠ INNER DEFENDER: chain failure"]`;
  assert `packet["trust_level"] == 0`, `state.clean_nrem_streak == 0`,
  `state.last_demotion_reason` contains "inner defender"
- `test_no_demotion_when_reactive` — trust already 0, defender_alerts present → no error,
  trust stays 0
- `test_no_demotion_on_empty_alerts` — `defender_alerts=[]` → trust unchanged

**Packet injection:**

- `test_keeper_context_in_packet` — call `process({})`;
  assert `"trust_level"` in packet and `"keeper_context"` in packet
- `test_keeper_context_appended_to_memory_context` — pass packet with
  `memory_context="prior context"`; after `process`, assert `memory_context` contains
  both "prior context" and the keeper context string

**Background tick:**

- `test_background_tick_updates_streak` — inject reader returning 4 clean entries;
  run `asyncio.run(keeper.background_tick(mock_queue))`;
  assert `state.clean_nrem_streak == 4`
- `test_background_tick_submits_bid` — inject reader returning 3 clean entries;
  after background_tick, verify mock_queue received a bid with correct coordinator_name

**`_compute_clean_streak`:**

- `test_compute_streak_empty` → 0
- `test_compute_streak_all_clean` — 5 entries all `chain_ok: True` → 5
- `test_compute_streak_one_failure` — 5 entries, entry 3 has `chain_ok: False` → 2
  (only entries 4 and 5 count)
- `test_compute_streak_failure_is_last` — last entry has `chain_ok: False` → 0

---

## Verification

```
pytest tests/test_keeper.py --basetemp .tmp/pytest_codex_task49 -v
pytest tests/test_awareness_orientation.py --basetemp .tmp/pytest_codex_task49 -v
pytest --ignore=tests/test_graph.py --basetemp .tmp/pytest_codex_task49 -v
```

Confirm `world_models/config.py` is NOT staged:
```
git status
```

Commit:
```
git commit -m "feat: Keeper coordinator — trust escalation protocol (Task 49)"
```

---

## Summary of changes

| File | Change |
|---|---|
| `coordinators/keeper.py` | New file — full Keeper coordinator |
| `coordinators/awareness.py` | Add `keeper` param to `__init__`; wire into `synchronous_run` after Orientation |
| `COORDINATOR_REGISTRY.md` | Register Keeper |
| `tests/test_keeper.py` | New — ~15 unit tests |
