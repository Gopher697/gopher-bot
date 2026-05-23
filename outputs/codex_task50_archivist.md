# Codex Task 50 — Archivist Coordinator: Self-Discovered Knowledge Stream

## Context

Gopher-bot currently learns things in foreground turns but never autonomously records *what*
was learned or *why it was significant*. The Archivist is the background coordinator that
closes this gap: it reads the turn audit log (built in Task 54), identifies noteworthy turns,
and creates LearningEpisode + Source nodes in the epistemic graph (built in Task 65) while
writing a flat research log as the primary audit trail.

This is the *creation side* of the epistemic chain. Ethos (Task 66) is the consumption side
(reads Doctrine nodes at runtime). Archivist is what drives knowledge from raw turns into the
epistemic chain over time.

**Primary data source:** `logs/audit/turns.jsonl` (one entry per foreground turn, written by
Awareness since Task 54). Each entry has `turn_id`, `session_id`, `orientation_active_goal`,
`prediction_accuracy_ema`, `has_error`, `trust_level`, etc.

**Primary output:** `logs/archivist/research.jsonl` — the self-discovered knowledge stream log.

**Secondary output:** LearningEpisode + Source nodes written to Neo4j (best-effort; wrapped
in try/except; not required for the log write to succeed).

**What makes a turn "noteworthy":**
1. `orientation_active_goal` is non-empty and >= `ARCHIVIST_MIN_GOAL_LENGTH` chars, OR
2. `prediction_accuracy_ema` < `ARCHIVIST_LOW_EMA_THRESHOLD` (model confusion — worth recording), OR
3. `has_error is True` (failure worth understanding)

Archivist processes turns in batches of `ARCHIVIST_BATCH_SIZE` per tick, tracking the last
processed `turn_id` so it doesn't re-process the same turns.

---

## Security invariant — check before every commit

`world_models/config.py` is gitignored and contains Neo4j credentials and API keys.
Run `git status` before committing. If `world_models/config.py` appears, STOP — do not commit.

---

## Part 1: `coordinators/archivist.py` — new file

### Constants

```python
ARCHIVIST_CADENCE_SECONDS = 300     # run every 5 minutes
ARCHIVIST_PRIORITY = 5              # between Keeper (4) and Drive (6)
ARCHIVIST_BATCH_SIZE = 10           # max turns processed per tick
ARCHIVIST_LOW_EMA_THRESHOLD = 0.30  # EMA below this → noteworthy
ARCHIVIST_MIN_GOAL_LENGTH = 5       # min chars in active_goal to be interesting

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARCHIVIST_RESEARCH_LOG_PATH = _PROJECT_ROOT / "logs" / "archivist" / "research.jsonl"
```

### `ArchivistState` dataclass

```python
@dataclass
class ArchivistState:
    last_processed_turn_id: str = ""   # turn_id of the last turn archived
    research_count: int = 0            # total research entries created this session
    last_tick: datetime | None = None
    last_bid_content: str | None = None
```

### `ArchivistBid` frozen dataclass

```python
@dataclass(frozen=True)
class ArchivistBid:
    coordinator_name: str
    content: str
    priority: int
    timestamp: float
    source: str = "archivist"
    type: str = "research_signal"
```

### `Archivist` class

```python
class Archivist(Coordinator):
    name = "archivist"

    def __init__(
        self,
        turn_log_reader: Callable[[int], list[dict]] | None = None,
        research_log_writer: Callable[[dict], None] | None = None,
        graph_writer: Callable[[str, str, str, str, str | None], tuple[str, str]] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        import time as _time
        self.turn_log_reader = turn_log_reader or _default_turn_log_reader
        self.research_log_writer = research_log_writer or _default_research_log_writer
        self.graph_writer = graph_writer or _default_graph_writer
        self.clock = clock or (lambda: datetime.now(UTC))
        self.state = ArchivistState()
```

### Module-level helpers

#### `_default_turn_log_reader(limit: int) -> list[dict]`

```python
def _default_turn_log_reader(limit: int) -> list[dict]:
    from coordinators.base import read_turn_log_entries
    return read_turn_log_entries(limit=limit)
```

#### `_default_research_log_writer(entry: dict) -> None`

```python
def _default_research_log_writer(entry: dict) -> None:
    import json
    path = ARCHIVIST_RESEARCH_LOG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
```

#### `_default_graph_writer(session_id, environment, coordinator, active_goal, turn_id) -> tuple[str, str]`

Creates a Source node (type="internal") and LearningEpisode node (type="autonomous") in the
graph. Returns `(source_id, learning_id)`. On any exception, returns `("", "")`.

```python
def _default_graph_writer(
    session_id: str,
    environment: str,
    coordinator: str,
    active_goal: str,
    turn_id: str | None,
) -> tuple[str, str]:
    try:
        from world_models import config, graph
        driver = graph.connect()
        try:
            with driver.session(database=config.NEO4J_DATABASE) as _session_unused:
                pass  # just checking connectivity
        finally:
            pass

        source_id = graph.create_source(
            driver=driver,
            title=active_goal or "Autonomous observation",
            source_type="internal",
            environment=environment,
            summary=f"Self-generated research note from turn {turn_id or 'unknown'}",
        )
        learning_id = graph.create_learning_episode(
            driver=driver,
            session_id=session_id,
            environment=environment,
            coordinator=coordinator,
            learning_type="autonomous",
            source_id=source_id,
            turn_id=turn_id,
            summary=active_goal or "Autonomous learning event",
        )
        graph.link_learning_episode_to_source(driver, learning_id, source_id, environment)
        graph.close(driver)
        return source_id, learning_id
    except Exception:
        return "", ""
```

### `Archivist.process(packet: dict) -> dict`

Foreground method. Minimal: adds `archivist_research_count` to packet from current session state.
The real work happens in `background_tick`.

```python
def process(self, packet: dict) -> dict:
    packet["archivist_research_count"] = self.state.research_count
    return packet
```

### `Archivist.background_tick(awareness_queue) -> None`

```python
async def background_tick(self, awareness_queue) -> None:
    self.state.last_tick = self.clock()
    turns = self.turn_log_reader(ARCHIVIST_BATCH_SIZE * 3)  # read more, filter down

    # Identify unprocessed noteworthy turns.
    new_turns = _filter_unprocessed(turns, self.state.last_processed_turn_id)
    noteworthy = [t for t in new_turns if _is_noteworthy(t)][:ARCHIVIST_BATCH_SIZE]

    if not noteworthy:
        return

    archived_count = 0
    last_turn_id = self.state.last_processed_turn_id

    for turn in noteworthy:
        entry = _build_research_entry(turn, self.graph_writer)
        try:
            self.research_log_writer(entry)
            archived_count += 1
            self.state.research_count += 1
        except Exception:
            continue
        turn_id = str(turn.get("turn_id") or "")
        if turn_id:
            last_turn_id = turn_id

    if last_turn_id:
        self.state.last_processed_turn_id = last_turn_id

    if archived_count > 0:
        observation = f"Archivist: filed {archived_count} research entr{'y' if archived_count == 1 else 'ies'} from turn log. Total this session: {self.state.research_count}."
        if observation != self.state.last_bid_content:
            import time as _time
            bid = ArchivistBid(
                coordinator_name=self.name,
                content=observation,
                priority=ARCHIVIST_PRIORITY,
                timestamp=_time.time(),
            )
            awareness_queue.submit(bid)
            self.state.last_bid_content = observation
```

### Module-level helpers (continued)

#### `_filter_unprocessed(turns: list[dict], last_processed_turn_id: str) -> list[dict]`

If `last_processed_turn_id` is empty, return all turns.
Otherwise, find the index of `last_processed_turn_id` in the list and return everything after it.
If not found, return all turns (safe default — mild re-processing risk, not harmful).

```python
def _filter_unprocessed(turns: list[dict], last_processed_turn_id: str) -> list[dict]:
    if not last_processed_turn_id:
        return list(turns)
    for i, turn in enumerate(turns):
        if str(turn.get("turn_id") or "") == last_processed_turn_id:
            return turns[i + 1:]
    return list(turns)
```

#### `_is_noteworthy(turn: dict) -> bool`

```python
def _is_noteworthy(turn: dict) -> bool:
    if turn.get("has_error"):
        return True
    active_goal = str(turn.get("orientation_active_goal") or "")
    if len(active_goal) >= ARCHIVIST_MIN_GOAL_LENGTH:
        return True
    ema = float(turn.get("prediction_accuracy_ema") or 0.5)
    if ema < ARCHIVIST_LOW_EMA_THRESHOLD:
        return True
    return False
```

#### `_build_research_entry(turn: dict, graph_writer: Callable) -> dict`

```python
def _build_research_entry(turn: dict, graph_writer: Callable) -> dict:
    import uuid
    from datetime import UTC, datetime

    turn_id = str(turn.get("turn_id") or "")
    session_id = str(turn.get("session_id") or "")
    active_goal = str(turn.get("orientation_active_goal") or "")
    ema = float(turn.get("prediction_accuracy_ema") or 0.5)
    has_error = bool(turn.get("has_error"))

    # Determine trigger reason
    triggers = []
    if has_error:
        triggers.append("error")
    if len(active_goal) >= ARCHIVIST_MIN_GOAL_LENGTH:
        triggers.append("goal_progress")
    if ema < ARCHIVIST_LOW_EMA_THRESHOLD:
        triggers.append("low_accuracy")

    # Attempt graph write (best-effort)
    source_id, learning_id = graph_writer(
        session_id, "global", "archivist", active_goal, turn_id or None
    )

    return {
        "research_id": uuid.uuid4().hex,
        "timestamp": datetime.now(UTC).isoformat(),
        "turn_id": turn_id,
        "session_id": session_id,
        "trigger": ",".join(triggers) or "unknown",
        "active_goal": active_goal,
        "prediction_accuracy_ema": round(ema, 4),
        "has_error": has_error,
        "source_id": source_id,
        "learning_id": learning_id,
        "status": "filed",
    }
```

---

## Part 2: Register Archivist in `coordinators/brain_loop.py`

### Import constant

```python
from coordinators.archivist import ARCHIVIST_CADENCE_SECONDS
```

### Add to `BACKGROUND_INTERVALS`

```python
BACKGROUND_INTERVALS = {
    ...
    "archivist": ARCHIVIST_CADENCE_SECONDS,
}
```

### Add to `BACKGROUND_COORDINATORS`

```python
BACKGROUND_COORDINATORS = (
    "feeling", "neuromodulation", "mirror_user", "mirror_self",
    "pattern_monitor", "curiosity", "drive", "dream", "keeper",
    "archivist",   # <-- add
)
```

### Add to `_default_background_coordinators()`

```python
from coordinators.archivist import Archivist
...
return {
    ...
    "archivist": Archivist(),
    ...
}
```

---

## Part 3: Update `COORDINATOR_REGISTRY.md`

Add Archivist after the Ethos entry. Follow the exact table format.

Key fields:
- **name:** `archivist`
- **Status:** Active — built (`coordinators/archivist.py`)
- **Model tier:** Tier 0 — no LLM calls; reads `logs/audit/turns.jsonl`; writes `logs/archivist/research.jsonl` and optional Neo4j nodes
- **Primary role:** Self-discovered knowledge stream. Reads the turn audit log to identify
  noteworthy turns (active goal progress, low prediction accuracy, errors). Creates LearningEpisode
  and Source nodes in the epistemic graph. Maintains a flat research log as the primary
  artifact.
- **Background cadence:** 300s
- **Notes:** Creation side of the epistemic chain. Ethos is the consumption side. Claim
  extraction and Belief promotion are future enhancements.

---

## Part 4: Tests — `tests/test_archivist.py` (new file)

All pure Python. Injectable `turn_log_reader`, `research_log_writer`, `graph_writer`. No disk,
no Neo4j.

**`_is_noteworthy`:**
- `test_noteworthy_on_error` — `has_error=True` → True
- `test_noteworthy_on_active_goal` — `orientation_active_goal="write keeper"` → True
- `test_noteworthy_on_low_ema` — `prediction_accuracy_ema=0.1` → True
- `test_not_noteworthy_empty_turn` — all defaults → False
- `test_not_noteworthy_short_goal` — goal `"ok"` (2 chars < 5) → False

**`_filter_unprocessed`:**
- `test_filter_no_last_id` — empty `last_processed_turn_id` → returns all
- `test_filter_skips_processed` — 5 turns, last_id = turns[2]["turn_id"] → returns turns[3:]
- `test_filter_id_not_found` — last_id not in list → returns all (safe default)
- `test_filter_empty_list` — `[]` → `[]`

**`_build_research_entry`:**
- `test_build_entry_has_required_keys` — call with minimal turn dict → "research_id", "turn_id",
  "session_id", "trigger", "active_goal", "status" all present
- `test_build_entry_trigger_error` — `has_error=True` → "error" in trigger
- `test_build_entry_trigger_goal` — active_goal >= 5 chars → "goal_progress" in trigger
- `test_build_entry_trigger_low_ema` — ema=0.1 → "low_accuracy" in trigger
- `test_build_entry_status_filed` → `entry["status"] == "filed"`

**`Archivist.background_tick`:**
- `test_background_tick_no_noteworthy_no_bid` — reader returns empty list → bid_queue empty,
  research_log_writer not called
- `test_background_tick_archives_noteworthy_turns` — reader returns 2 noteworthy turns →
  research_log_writer called twice, bid submitted with count in content
- `test_background_tick_updates_last_processed_turn_id` — after tick with 2 turns →
  `state.last_processed_turn_id` == last turn's turn_id
- `test_background_tick_respects_batch_size` — reader returns 20 noteworthy turns →
  archived count <= `ARCHIVIST_BATCH_SIZE`

**`Archivist.process`:**
- `test_process_adds_research_count` — `process({})` → `packet["archivist_research_count"] == 0`

---

## Verification

```
pytest tests/test_archivist.py --basetemp .tmp/pytest_codex_task50 -v
pytest tests/test_awareness_orientation.py --basetemp .tmp/pytest_codex_task50 -v
pytest --ignore=tests/test_graph.py --basetemp .tmp/pytest_codex_task50 -v
```

Confirm `world_models/config.py` is NOT staged:
```
git status
```

Commit:
```
git commit -m "feat: Archivist coordinator — self-discovered knowledge stream + research log (Task 50)"
```

---

## Summary of changes

| File | Change |
|---|---|
| `coordinators/archivist.py` | New file — full Archivist coordinator |
| `coordinators/brain_loop.py` | Add `ARCHIVIST_CADENCE_SECONDS` import; add "archivist" to `BACKGROUND_INTERVALS`, `BACKGROUND_COORDINATORS`, and `_default_background_coordinators()` |
| `COORDINATOR_REGISTRY.md` | Register Archivist |
| `tests/test_archivist.py` | New — ~17 unit tests |
