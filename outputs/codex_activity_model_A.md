# Codex Task: Activity Model — Part A (Schema + Recognition)

This is the first of two tasks implementing the Activity model, the executive function
layer described in `docs/activity_model_design.md`. Read that document before starting.

Task A scope: Activity node schema in Neo4j, detection logic in Awareness, reminder
firing via background tick. No coordinator context injection yet (that is Task B).

---

## Context

The bot currently has no model of what it is doing at any given moment. It reacts to
each input in isolation, losing board state between turns, failing to fire reminders
proactively, and never calling `record_skill_practice()` because nothing knows when a
"practice session" is occurring. The Activity model is the fix for all of this.

This task is **domain-agnostic** — Activity applies to games, work tasks, research,
reminders, monitoring, and everything else. Do not over-index on chess.

---

## Files to modify

1. `world_models/graph.py` — 5 new functions for Activity CRUD
2. `coordinators/awareness.py` — activity registry + detection + reminder check
3. `coordinators/brain_loop.py` — reminder check on background tick
4. `tests/test_activity_model.py` — new file, 9 tests

Do not modify any other files.

---

## 1. `world_models/graph.py`

Add the following after the existing Skill functions (after `get_skills_for_coordinator`).
Do not touch any existing functions.

### Constants (add near the top with other VALID_* sets)

```python
VALID_ACTIVITY_TYPES = {"game", "task", "reminder", "autonomous", "monitoring", "conversation"}
VALID_ACTIVITY_STATUSES = {"active", "dormant", "completed"}
```

### Function 1: `create_activity`

```python
def create_activity(
    driver,
    *,
    activity_id: str,
    environment: str,
    type: str,
    name: str,
    status: str = "active",
    created_at: float,
    updated_at: float,
    goals: str = "[]",           # JSON list string
    skill_domains: str = "[]",   # JSON list string
    state: str = "{}",           # JSON dict string
    trigger_at: float | None = None,
    completed_at: float | None = None,
    parent_id: str | None = None,
) -> None:
    """
    Create an Activity node in Neo4j. Caller is responsible for generating activity_id.
    Does not validate type/status — caller must validate before calling.
    """
    props = {
        "activity_id": activity_id,
        "environment": environment,
        "type": type,
        "name": name,
        "status": status,
        "created_at": created_at,
        "updated_at": updated_at,
        "goals": goals,
        "skill_domains": skill_domains,
        "state": state,
        "trigger_at": trigger_at,
        "completed_at": completed_at,
        "parent_id": parent_id,
    }

    def write(tx):
        tx.run("CREATE (a:Activity $props)", props=props)

    with _session(driver) as session:
        session.execute_write(write)
        _audit_after_graph_write("create_activity", "Activity", props)
```

### Function 2: `get_activity`

```python
def get_activity(
    driver,
    activity_id: str,
    environment: str,
) -> dict | None:
    """
    Return the Activity node as a plain dict, or None if not found.
    """
    def read(tx):
        result = tx.run(
            """
            MATCH (a:Activity {activity_id: $activity_id, environment: $environment})
            RETURN a
            """,
            activity_id=activity_id,
            environment=environment,
        )
        record = result.single()
        return dict(record["a"]) if record else None

    with _session(driver) as session:
        return session.execute_read(read)
```

### Function 3: `update_activity_status`

```python
def update_activity_status(
    driver,
    activity_id: str,
    environment: str,
    status: str,
    updated_at: float,
    completed_at: float | None = None,
) -> bool:
    """
    Update status (and optionally completed_at) on an Activity node.
    Returns True if the node was found and updated.
    """
    def write(tx):
        result = tx.run(
            """
            MATCH (a:Activity {activity_id: $activity_id, environment: $environment})
            SET a.status = $status,
                a.updated_at = $updated_at,
                a.completed_at = $completed_at
            RETURN count(a) AS matched
            """,
            activity_id=activity_id,
            environment=environment,
            status=status,
            updated_at=updated_at,
            completed_at=completed_at,
        )
        record = result.single()
        return bool(record and record["matched"] > 0)

    with _session(driver) as session:
        matched = session.execute_write(write)
        if matched:
            _audit_after_graph_write(
                "update_activity_status", "Activity",
                {"activity_id": activity_id, "status": status}
            )
        return matched
```

### Function 4: `update_activity_state`

```python
def update_activity_state(
    driver,
    activity_id: str,
    environment: str,
    state_patch: dict,
    updated_at: float,
) -> bool:
    """
    Merge state_patch into the Activity's JSON state dict (shallow merge).
    Returns True if the node was found and updated.
    """
    import json as _json

    def write(tx):
        # Read current state
        result = tx.run(
            "MATCH (a:Activity {activity_id: $id, environment: $env}) RETURN a.state AS state",
            id=activity_id,
            env=environment,
        )
        record = result.single()
        if not record:
            return False
        try:
            current = _json.loads(record["state"] or "{}")
        except (ValueError, TypeError):
            current = {}
        current.update(state_patch)
        new_state = _json.dumps(current)
        tx.run(
            """
            MATCH (a:Activity {activity_id: $id, environment: $env})
            SET a.state = $state, a.updated_at = $updated_at
            """,
            id=activity_id,
            env=environment,
            state=new_state,
            updated_at=updated_at,
        )
        return True

    with _session(driver) as session:
        return session.execute_write(write)
```

### Function 5: `get_due_reminders`

```python
def get_due_reminders(
    driver,
    environment: str,
    now_ts: float,
) -> list[dict]:
    """
    Return Activity nodes of type "reminder" with status "active" and
    trigger_at <= now_ts. Results sorted by trigger_at ascending.
    """
    def read(tx):
        result = tx.run(
            """
            MATCH (a:Activity {type: "reminder", status: "active", environment: $env})
            WHERE a.trigger_at IS NOT NULL AND a.trigger_at <= $now
            RETURN a
            ORDER BY a.trigger_at ASC
            """,
            env=environment,
            now=now_ts,
        )
        return [dict(r["a"]) for r in result]

    with _session(driver) as session:
        return session.execute_read(read)
```

---

## 2. `coordinators/awareness.py`

### 2a. Add imports (at the top with existing imports)

```python
import json as _json
import re as _re
import uuid as _uuid_mod
```

(Note: `uuid` is already imported as `_uuid`. Use `_uuid_mod` to avoid collision, or
just use the existing `_uuid` import — whichever avoids conflict.)

### 2b. Add to `Awareness.__init__`

After `self.drive = drive or Drive()`, add:

```python
# Activity model — in-memory registry
# Keys: (type, context_key) → activity_id
# Order: most recently active first
self._activity_registry: dict[tuple[str, str], str] = {}
self._activity_order: list[tuple[str, str]] = []
```

### 2c. Wire `_detect_activity` into `synchronous_run`

In `synchronous_run`, find the line `packet = self.memory.process(packet)`.
Insert the following **before** that line:

```python
# --- Activity detection --------------------------------------------------
# Runs before Memory so the detected activity can guide retrieval in Task B.
try:
    current_activity = self._detect_activity(packet)
    if current_activity:
        packet["current_activity"] = current_activity
except Exception:
    pass  # non-fatal — pipeline continues without activity context
# -------------------------------------------------------------------------
```

### 2d. New method: `_detect_activity`

Add to the `Awareness` class (private methods section, after `_drain_bids_into_packet`):

```python
def _detect_activity(self, packet: dict) -> dict | None:
    """
    Scan the packet for activity signals and return a current_activity dict,
    creating or resuming an Activity node in Neo4j as needed.

    Returns a dict with keys:
        type, context_key, activity_id, skill_domains (list), state (dict)
    Returns None only if Neo4j is unavailable.
    """
    message = str(packet.get("message") or "")
    visual_desc = ""
    vp = packet.get("visual_percept")
    if isinstance(vp, dict):
        visual_desc = str(vp.get("description") or "").lower()

    # --- Signal detection (most specific first) ---
    if _fen_pattern.search(message):
        activity_type = "game"
        context_key = "chess"
        skill_domains = ["chess"]
        fen_match = _fen_pattern.search(message)
        state: dict = {"fen": fen_match.group(0) if fen_match else ""}

    elif "chess board" in visual_desc or (
        "chess" in visual_desc and "board" in visual_desc
    ):
        activity_type = "game"
        context_key = "chess"
        skill_domains = ["chess"]
        state = {}

    elif _reminder_pattern.search(message):
        activity_type = "reminder"
        trigger_at = _parse_reminder_trigger(message, self._time_fn())
        context_key = f"reminder_{int(trigger_at or self._time_fn())}"
        skill_domains = []
        state = {"message": message, "trigger_at": trigger_at}

    elif _task_pattern.search(message):
        activity_type = "task"
        context_key = message[:60].strip()
        skill_domains = ["computer_use"]
        state = {"goal": message[:200]}

    else:
        activity_type = "conversation"
        context_key = str(packet.get("session_id") or "default")
        skill_domains = []
        state = {}

    key = (activity_type, context_key)
    now = self._time_fn()

    # --- Registry lookup ---
    if key in self._activity_registry:
        activity_id = self._activity_registry[key]
        # Bring to front of order list
        try:
            self._activity_order.remove(key)
        except ValueError:
            pass
        self._activity_order.insert(0, key)
        # Resume if dormant
        try:
            driver = _graph.connect()
            try:
                _graph.update_activity_status(
                    driver, activity_id, "global", "active", now
                )
            finally:
                _graph.close(driver)
        except Exception:
            pass
        return {
            "type": activity_type,
            "context_key": context_key,
            "activity_id": activity_id,
            "skill_domains": skill_domains,
            "state": state,
        }

    # --- Create new Activity node ---
    activity_id = _uuid_mod.uuid4().hex
    name = _activity_name(activity_type, context_key, now)
    import json as _j
    try:
        driver = _graph.connect()
        try:
            _graph.create_activity(
                driver,
                activity_id=activity_id,
                environment="global",
                type=activity_type,
                name=name,
                status="active",
                created_at=now,
                updated_at=now,
                skill_domains=_j.dumps(skill_domains),
                state=_j.dumps(state),
                trigger_at=state.get("trigger_at") if activity_type == "reminder" else None,
            )
        finally:
            _graph.close(driver)
    except Exception:
        # Graph unavailable — still track in registry with generated ID
        pass

    self._activity_registry[key] = activity_id
    self._activity_order.insert(0, key)

    return {
        "type": activity_type,
        "context_key": context_key,
        "activity_id": activity_id,
        "skill_domains": skill_domains,
        "state": state,
    }
```

### 2e. New method: `check_scheduled_activities`

```python
def check_scheduled_activities(self, bid_queue: Any) -> None:
    """
    Query Neo4j for due reminder Activities and submit a bid for each.
    Marks each fired reminder as completed. Called from BrainLoop background tick.
    """
    from coordinators.bid import Bid, PRIORITY_MIRROR

    now = self._time_fn()
    try:
        driver = _graph.connect()
        try:
            due = _graph.get_due_reminders(driver, "global", now)
        finally:
            _graph.close(driver)
    except Exception:
        return

    for activity in due:
        activity_id = activity.get("activity_id", "")
        try:
            raw_state = activity.get("state") or "{}"
            state = _json.loads(raw_state) if isinstance(raw_state, str) else {}
        except (ValueError, TypeError):
            state = {}
        reminder_message = str(state.get("message") or activity.get("name") or "Reminder")

        bid = Bid(
            coordinator_name="awareness_reminder",
            content=f"⏰ Reminder: {reminder_message}",
            priority=PRIORITY_MIRROR,
            timestamp=now,
        )
        try:
            bid_queue.submit(bid)
        except Exception:
            continue

        # Mark completed
        try:
            driver = _graph.connect()
            try:
                _graph.update_activity_status(
                    driver, activity_id, "global", "completed", now, completed_at=now
                )
            finally:
                _graph.close(driver)
        except Exception:
            pass

        # Remove from in-memory registry
        key = ("reminder", activity.get("context_key", ""))
        self._activity_registry.pop(key, None)
        try:
            self._activity_order.remove(key)
        except ValueError:
            pass
```

### 2f. Module-level helpers

Add at the **module level** in `awareness.py` (after imports, before the class):

```python
from world_models import graph as _graph

# ---------------------------------------------------------------------------
# Activity detection patterns
# ---------------------------------------------------------------------------

# Simplified FEN rank pattern: matches 8 slash-separated rank strings
# A rank is 1–8 characters from the set [prnbqkPRNBQK1-8]
_FEN_RANK = r"[prnbqkPRNBQK1-8]{1,8}"
_fen_pattern = _re.compile(
    rf"{_FEN_RANK}(?:/{_FEN_RANK}){{7}}"
)

_reminder_pattern = _re.compile(
    r"\b("
    r"remind me"
    r"|set (?:a )?(?:reminder|timer|alarm)"
    r"|in \d+ (?:second|minute|hour|day)s?"
    r"|at \d{1,2}:\d{2}"
    r"|tomorrow(?: at)?"
    r"|tonight"
    r")\b",
    _re.IGNORECASE,
)

_task_pattern = _re.compile(
    r"\b("
    r"(?:can you |please )?(?:open|launch|click|drag|type|navigate|go to)"
    r"|on my (?:computer|desktop|screen)"
    r"|do (?:this |that )?(?:for me )?on my"
    r")\b",
    _re.IGNORECASE,
)


def _parse_reminder_trigger(message: str, now: float) -> float | None:
    """
    Parse "in X minutes/hours/days" from message and return Unix timestamp.
    Returns None if no parseable duration found.
    """
    m = _re.search(
        r"\bin (\d+)\s*(second|minute|hour|day)s?\b",
        message,
        _re.IGNORECASE,
    )
    if not m:
        return None
    amount = int(m.group(1))
    unit = m.group(2).lower()
    multipliers = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}
    return now + amount * multipliers.get(unit, 60)


def _activity_name(activity_type: str, context_key: str, now: float) -> str:
    """Generate a human-readable activity name from type, context, and timestamp."""
    import datetime as _dt
    ts = _dt.datetime.fromtimestamp(now, tz=_dt.timezone.utc).strftime("%Y-%m-%d")
    label = context_key[:30] if context_key else activity_type
    return f"{activity_type} · {label} · {ts}"
```

---

## 3. `coordinators/brain_loop.py`

### 3a. Add reminder_check interval

In `BACKGROUND_INTERVALS`, add:

```python
"reminder_check": 10.0,
```

### 3b. Add reminder check to `tick_once`

At the **end** of `tick_once`, after the existing `for name, coordinator` loop, add:

```python
# --- Reminder Activity check ----------------------------------------------
# Runs on its own short interval independent of background coordinators.
if self.awareness is not None and self.bid_queue is not None:
    now = self.time_fn()
    last_reminder_check = self.last_ticks.get("reminder_check", 0.0)
    reminder_interval = self.intervals.get("reminder_check", 10.0)
    if now - last_reminder_check >= reminder_interval:
        try:
            self.awareness.check_scheduled_activities(self.bid_queue)
        except Exception:
            pass
        self.last_ticks["reminder_check"] = now
# -------------------------------------------------------------------------
```

---

## 4. `tests/test_activity_model.py`

Create this file. All tests must be free-standing (no live Neo4j; mock graph calls).

```python
"""Tests for Activity model — Part A (schema, recognition, reminder firing)."""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Detection helper tests (unit — no graph, no Awareness instance needed)
# ---------------------------------------------------------------------------

def test_fen_pattern_matches_valid_fen():
    """FEN string in message is detected by the regex."""
    from coordinators.awareness import _fen_pattern

    fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR"
    assert _fen_pattern.search(fen) is not None


def test_fen_pattern_does_not_match_plain_text():
    from coordinators.awareness import _fen_pattern

    assert _fen_pattern.search("Let's play chess today") is None


def test_reminder_pattern_matches_natural_language():
    from coordinators.awareness import _reminder_pattern

    cases = [
        "remind me in 10 minutes to check the server",
        "set a reminder for tomorrow at 9:00",
        "in 2 hours ping me",
    ]
    for msg in cases:
        assert _reminder_pattern.search(msg) is not None, f"Should match: {msg!r}"


def test_parse_reminder_trigger_minutes():
    from coordinators.awareness import _parse_reminder_trigger

    now = 1000.0
    result = _parse_reminder_trigger("remind me in 10 minutes", now)
    assert result == now + 10 * 60


def test_parse_reminder_trigger_hours():
    from coordinators.awareness import _parse_reminder_trigger

    now = 1000.0
    result = _parse_reminder_trigger("in 2 hours send me a note", now)
    assert result == now + 2 * 3600


def test_parse_reminder_trigger_no_match():
    from coordinators.awareness import _parse_reminder_trigger

    assert _parse_reminder_trigger("just a normal message", 1000.0) is None


# ---------------------------------------------------------------------------
# _detect_activity tests (Awareness instance with mocked graph)
# ---------------------------------------------------------------------------

def _make_awareness_no_graph():
    """Return an Awareness with all graph calls stubbed out."""
    from tests.conftest import isolated_awareness

    aw = isolated_awareness()
    return aw


def test_detect_activity_chess_fen(monkeypatch):
    """FEN in message → game activity, chess context key."""
    aw = _make_awareness_no_graph()

    monkeypatch.setattr("coordinators.awareness._graph.connect", lambda: MagicMock())
    monkeypatch.setattr("coordinators.awareness._graph.close", lambda d: None)
    monkeypatch.setattr(
        "coordinators.awareness._graph.create_activity",
        lambda *a, **kw: None,
    )

    packet = {
        "message": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 1",
        "session_id": "test-session",
    }
    result = aw._detect_activity(packet)
    assert result is not None
    assert result["type"] == "game"
    assert result["context_key"] == "chess"
    assert "chess" in result["skill_domains"]


def test_detect_activity_reminder_intent(monkeypatch):
    """Reminder phrase → reminder activity type with trigger_at set."""
    aw = _make_awareness_no_graph()

    monkeypatch.setattr("coordinators.awareness._graph.connect", lambda: MagicMock())
    monkeypatch.setattr("coordinators.awareness._graph.close", lambda d: None)
    monkeypatch.setattr(
        "coordinators.awareness._graph.create_activity",
        lambda *a, **kw: None,
    )

    packet = {
        "message": "remind me in 5 minutes to stretch",
        "session_id": "test-session",
    }
    result = aw._detect_activity(packet)
    assert result is not None
    assert result["type"] == "reminder"
    assert result["state"].get("trigger_at") is not None
    assert result["state"]["trigger_at"] > time.time()


def test_detect_activity_fallback_conversation(monkeypatch):
    """No recognized signal → conversation activity."""
    aw = _make_awareness_no_graph()

    monkeypatch.setattr("coordinators.awareness._graph.connect", lambda: MagicMock())
    monkeypatch.setattr("coordinators.awareness._graph.close", lambda d: None)
    monkeypatch.setattr(
        "coordinators.awareness._graph.create_activity",
        lambda *a, **kw: None,
    )

    packet = {"message": "What is the capital of France?", "session_id": "s1"}
    result = aw._detect_activity(packet)
    assert result is not None
    assert result["type"] == "conversation"


def test_detect_activity_registry_deduplication(monkeypatch):
    """Same FEN signal on second call returns same activity_id (no duplicate CREATE)."""
    aw = _make_awareness_no_graph()

    created = []

    def fake_create(*a, **kw):
        created.append(kw.get("activity_id"))

    monkeypatch.setattr("coordinators.awareness._graph.connect", lambda: MagicMock())
    monkeypatch.setattr("coordinators.awareness._graph.close", lambda d: None)
    monkeypatch.setattr("coordinators.awareness._graph.create_activity", fake_create)
    monkeypatch.setattr(
        "coordinators.awareness._graph.update_activity_status",
        lambda *a, **kw: True,
    )

    fen_msg = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 1"
    packet = {"message": fen_msg, "session_id": "s1"}

    r1 = aw._detect_activity(packet)
    r2 = aw._detect_activity(packet)

    assert r1["activity_id"] == r2["activity_id"]
    assert len(created) == 1  # CREATE called only once


# ---------------------------------------------------------------------------
# check_scheduled_activities tests
# ---------------------------------------------------------------------------

def test_reminder_fires_when_due(monkeypatch):
    """Due reminder Activity → bid submitted to bid_queue."""
    from coordinators.bid import BidQueue

    aw = _make_awareness_no_graph()
    bid_queue = BidQueue()

    import json
    now = time.time()
    due_reminder = {
        "activity_id": "abc123",
        "context_key": "reminder_1000",
        "state": json.dumps({"message": "stretch break", "trigger_at": now - 1}),
        "name": "reminder · stretch · 2026-05-25",
    }

    monkeypatch.setattr("coordinators.awareness._graph.connect", lambda: MagicMock())
    monkeypatch.setattr("coordinators.awareness._graph.close", lambda d: None)
    monkeypatch.setattr(
        "coordinators.awareness._graph.get_due_reminders",
        lambda *a, **kw: [due_reminder],
    )
    monkeypatch.setattr(
        "coordinators.awareness._graph.update_activity_status",
        lambda *a, **kw: True,
    )

    aw.check_scheduled_activities(bid_queue)

    bids = bid_queue.get_pending()
    assert len(bids) == 1
    assert "stretch break" in bids[0].content


def test_no_bids_when_no_due_reminders(monkeypatch):
    """No due reminders → bid_queue stays empty."""
    from coordinators.bid import BidQueue

    aw = _make_awareness_no_graph()
    bid_queue = BidQueue()

    monkeypatch.setattr("coordinators.awareness._graph.connect", lambda: MagicMock())
    monkeypatch.setattr("coordinators.awareness._graph.close", lambda d: None)
    monkeypatch.setattr(
        "coordinators.awareness._graph.get_due_reminders",
        lambda *a, **kw: [],
    )

    aw.check_scheduled_activities(bid_queue)
    assert bid_queue.empty()
```

---

## Tests to run

```
pytest tests/test_activity_model.py -v
pytest --basetemp .tmp/pytest-tmp -q
```

All 1031 existing tests must still pass. The new file adds 9 tests for a total of 1040.

---

## Security reminder

Do not stage or commit `world_models/config.py`.

---

## Commit instructions

```
git status
# Verify world_models/config.py is NOT staged.

git add world_models/graph.py coordinators/awareness.py coordinators/brain_loop.py tests/test_activity_model.py
git commit -m "feat: Activity model Part A — schema, detection, reminder firing

- graph.py: create_activity, get_activity, update_activity_status,
  update_activity_state, get_due_reminders; VALID_ACTIVITY_TYPES/STATUSES
- awareness.py: _activity_registry dict, _detect_activity() with FEN/
  reminder/task/conversation signal recognition, check_scheduled_activities()
  for proactive reminder bid submission; module-level regex patterns +
  _parse_reminder_trigger, _activity_name helpers
- brain_loop.py: reminder_check interval (10s) in BACKGROUND_INTERVALS;
  tick_once calls awareness.check_scheduled_activities on that interval
- 9 new tests (1040 total)"
git push origin main
```
