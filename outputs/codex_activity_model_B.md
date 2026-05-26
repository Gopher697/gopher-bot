# Codex Task: Activity Model — Part B (Coordinator Wiring)

This is the second of two tasks implementing the Activity model. **Task A must be
committed and passing before starting this task.** Read `docs/activity_model_design.md`
before starting.

Task B scope: wire `packet["current_activity"]` (written by Task A's `_detect_activity`)
into the four downstream coordinators — Orientation, Hands, Reason, Memory.

---

## Context

After Task A, every turn has `packet["current_activity"]` set (if detection succeeded).
It is a dict:
```python
{
    "type": "game" | "task" | "reminder" | "autonomous" | "monitoring" | "conversation",
    "context_key": str,
    "activity_id": str,
    "skill_domains": list[str],   # e.g. ["chess"]
    "state": dict,                # e.g. {"fen": "..."}
}
```

Task B makes each coordinator aware of this context.

---

## Files to modify

1. `coordinators/orientation.py` — inject activity into orientation digest
2. `coordinators/hands.py` — update activity state after successful actions
3. `coordinators/reason.py` — auto-record skill practice for game/learning turns
4. `coordinators/memory.py` — boost keyword retrieval with skill domains
5. `tests/test_activity_model_wiring.py` — new file, 9 tests

Do not modify any other files.

---

## 1. `coordinators/orientation.py`

### 1a. Add `current_activity` to the orientation dict

In `_build_orientation_dict()`, add one key to the returned dict:

```python
# Add alongside the existing keys:
"current_activity": packet.get("current_activity"),
```

### 1b. Add activity section to `_format_orientation_context`

In `_format_orientation_context(orientation)`, add the following block **after** the
`"Operational:"` line and **before** the `"Active goal focus:"` block:

```python
activity = orientation.get("current_activity")
if isinstance(activity, dict) and activity.get("type") and activity["type"] != "conversation":
    act_type = activity["type"]
    context_key = activity.get("context_key", "")
    skill_domains = activity.get("skill_domains") or []
    state = activity.get("state") or {}

    act_lines = [f"Activity: {act_type} [{context_key}]"]
    if act_type == "game" and state.get("fen"):
        act_lines.append(f"  Board: {state['fen']}")
    if skill_domains:
        act_lines.append(f"  Skills: {', '.join(skill_domains)}")
    if act_type == "reminder" and state.get("message"):
        act_lines.append(f"  Pending: {state['message']}")
    lines.append("\n".join(act_lines))
```

Rationale: `conversation` activities are not injected — they are the default and add
no information. All other types tell Reason something meaningful about what it is doing.

---

## 2. `coordinators/hands.py`

### 2a. Add `_update_activity_state` method

Add to the `Hands` class (alongside other private methods):

```python
def _update_activity_state(self, packet: dict, state_patch: dict) -> None:
    """
    Shallow-merge state_patch into the current Activity node in Neo4j.
    Silent no-op if no current activity, no activity_id, or graph unavailable.
    """
    activity = packet.get("current_activity")
    if not isinstance(activity, dict):
        return
    activity_id = activity.get("activity_id")
    if not activity_id:
        return
    import time as _t
    now = _t.time()
    try:
        from world_models import graph as _g
        driver = _g.connect()
        try:
            _g.update_activity_state(driver, activity_id, "global", state_patch, now)
        finally:
            _g.close(driver)
    except Exception:
        pass
```

### 2b. Call `_update_activity_state` in `process()`

In `Hands.process()`, after `packet["action_result"] = result` (the last line before
`return packet`), add:

```python
# Patch activity state with the last executed action type.
# This records what the bot did most recently within the activity context,
# without overwriting domain-specific state (e.g. chess FEN).
if result.get("status") == "executed":
    self._update_activity_state(packet, {"last_action": action_type})
```

---

## 3. `coordinators/reason.py`

### 3a. Add `_record_activity_skills` method

Add to the `Reason` class (alongside other private methods):

```python
def _record_activity_skills(self, activity: dict) -> None:
    """
    Look up or create a Skill node for each skill domain in this activity,
    then record one practice event (success=True, outcome pending).

    Called only for game and learning activity types — this is the auto-wiring
    that replaces the manual per-coordinator record_skill_practice() call.
    """
    import json as _j
    skill_domains = activity.get("skill_domains") or []
    if isinstance(skill_domains, str):
        try:
            skill_domains = _j.loads(skill_domains)
        except (ValueError, TypeError):
            skill_domains = []

    if not skill_domains:
        return

    environment = "global"
    for domain in skill_domains:
        domain = str(domain).strip()
        if not domain:
            continue
        try:
            from world_models import graph as _g
            driver = _g.connect()
            try:
                # Find existing Skill node for this domain owned by this coordinator
                existing = _g.get_skills_for_coordinator(driver, "reason", environment)
                match = next(
                    (s for s in existing if s.get("domain") == domain), None
                )
                if match:
                    skill_id = match["skill_id"]
                else:
                    skill_id = _g.create_skill(
                        driver,
                        coordinator="reason",
                        skill_name=domain,
                        domain=domain,
                        environment=environment,
                    )
                _g.record_skill_practice(driver, skill_id, environment, success=True)
            finally:
                _g.close(driver)
        except Exception:
            pass  # non-fatal — skill recording failure does not block the turn
```

### 3b. Call `_record_activity_skills` in `process()`

In `Reason.process()`, after `packet["reason_output"] = response`, add:

```python
# Auto-record skill practice for game and learning activities.
# This is the execution site for the Activity model's skill wiring.
_act = packet.get("current_activity")
if isinstance(_act, dict) and _act.get("type") in ("game", "learning"):
    self._record_activity_skills(_act)
```

---

## 4. `coordinators/memory.py`

### 4a. Boost keyword retrieval from activity skill domains

In `Memory.process()`, replace the existing keyword extraction:

```python
# BEFORE:
def process(self, packet: dict) -> dict:
    keywords = packet.get("keywords") or []
    packet["memory_context"] = self.retrieve(keywords)
```

```python
# AFTER:
def process(self, packet: dict) -> dict:
    keywords = list(packet.get("keywords") or [])

    # Boost retrieval with skill domains from the current activity.
    # A chess game should surface chess memories; a coding task should surface
    # relevant code patterns. Append domains as additional keyword signals.
    _act = packet.get("current_activity")
    if isinstance(_act, dict):
        import json as _j
        skill_domains = _act.get("skill_domains") or []
        if isinstance(skill_domains, str):
            try:
                skill_domains = _j.loads(skill_domains)
            except (ValueError, TypeError):
                skill_domains = []
        for domain in skill_domains:
            domain = str(domain).strip()
            if domain and domain not in keywords:
                keywords.append(domain)

    packet["memory_context"] = self.retrieve(keywords)
```

The rest of `Memory.process()` (attachment ingestion) is unchanged.

---

## 5. `tests/test_activity_model_wiring.py`

Create this file. All tests must be free-standing (no live Neo4j).

```python
"""Tests for Activity model Part B — coordinator wiring."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Orientation wiring tests
# ---------------------------------------------------------------------------

def test_orientation_injects_game_activity_into_context():
    """Active game activity appears in orientation_context seen by Reason."""
    from coordinators.orientation import _format_orientation_context

    orientation = {
        "thread_context": None,
        "operational_context": "Process up 0h1m | NREM: never run",
        "active_goal_focus": None,
        "relevant_goals": [],
        "do_not_forget": [],
        "background_pressures": [],
        "recommended_next_pressure": None,
        "recent_shift": None,
        "current_activity": {
            "type": "game",
            "context_key": "chess",
            "skill_domains": ["chess"],
            "state": {"fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR"},
        },
    }
    ctx = _format_orientation_context(orientation)
    assert "Activity: game [chess]" in ctx
    assert "rnbqkbnr" in ctx
    assert "chess" in ctx


def test_orientation_suppresses_conversation_activity():
    """Conversation activities do not add noise to orientation context."""
    from coordinators.orientation import _format_orientation_context

    orientation = {
        "thread_context": None,
        "operational_context": "Process up 0h1m",
        "active_goal_focus": None,
        "relevant_goals": [],
        "do_not_forget": [],
        "background_pressures": [],
        "recommended_next_pressure": None,
        "recent_shift": None,
        "current_activity": {
            "type": "conversation",
            "context_key": "abc123",
            "skill_domains": [],
            "state": {},
        },
    }
    ctx = _format_orientation_context(orientation)
    assert "Activity:" not in ctx


def test_orientation_injects_reminder_pending_message():
    """Reminder activity shows its message in orientation context."""
    from coordinators.orientation import _format_orientation_context

    orientation = {
        "thread_context": None,
        "operational_context": "Process up 0h1m",
        "active_goal_focus": None,
        "relevant_goals": [],
        "do_not_forget": [],
        "background_pressures": [],
        "recommended_next_pressure": None,
        "recent_shift": None,
        "current_activity": {
            "type": "reminder",
            "context_key": "reminder_1000",
            "skill_domains": [],
            "state": {"message": "check the build logs", "trigger_at": 9999999.0},
        },
    }
    ctx = _format_orientation_context(orientation)
    assert "reminder" in ctx
    assert "check the build logs" in ctx


# ---------------------------------------------------------------------------
# Hands wiring tests
# ---------------------------------------------------------------------------

def test_hands_updates_activity_state_on_successful_action(monkeypatch):
    """Successful whitelist action → _update_activity_state called with last_action."""
    from coordinators.hands import Hands

    updated = []

    def fake_update_activity_state(self_inner, packet, patch):
        updated.append(patch)

    monkeypatch.setattr(Hands, "_update_activity_state", fake_update_activity_state)

    hands = Hands()
    packet = {
        "action": {"type": "screenshot", "args": {}},
        "current_activity": {
            "type": "game",
            "activity_id": "abc123",
            "skill_domains": ["chess"],
            "state": {},
        },
    }
    hands.process(packet)

    assert len(updated) == 1
    assert updated[0].get("last_action") == "screenshot"


def test_hands_skips_activity_update_when_action_blocked(monkeypatch):
    """Blocked actions do not trigger activity state update."""
    from coordinators.hands import Hands

    updated = []

    def fake_update(self_inner, packet, patch):
        updated.append(patch)

    monkeypatch.setattr(Hands, "_update_activity_state", fake_update)

    hands = Hands()
    # delete_file is blacklisted
    packet = {
        "action": {"type": "delete_file", "args": {"path": "/tmp/x"}},
        "current_activity": {
            "type": "task",
            "activity_id": "xyz",
            "skill_domains": [],
            "state": {},
        },
    }
    hands.process(packet)
    assert updated == []


# ---------------------------------------------------------------------------
# Reason wiring tests
# ---------------------------------------------------------------------------

def test_reason_records_skill_practice_for_game_activity(monkeypatch):
    """Game activity → _record_activity_skills called after response generation."""
    from coordinators.reason import Reason
    from coordinators.memory import Memory

    recorded = []

    def fake_record(self_inner, activity):
        recorded.append(activity)

    monkeypatch.setattr(Reason, "_record_activity_skills", fake_record)
    monkeypatch.setattr(
        Reason, "generate_response", lambda *a, **kw: "test response"
    )

    reason = Reason(memory=Memory())
    packet = {
        "message": "what should I do next?",
        "memory_context": "",
        "tier": 1,
        "current_activity": {
            "type": "game",
            "context_key": "chess",
            "activity_id": "abc",
            "skill_domains": ["chess"],
            "state": {},
        },
    }
    reason.process(packet)
    assert len(recorded) == 1
    assert recorded[0]["type"] == "game"


def test_reason_skips_skill_recording_for_conversation(monkeypatch):
    """Conversation activity does not trigger skill recording."""
    from coordinators.reason import Reason
    from coordinators.memory import Memory

    recorded = []

    def fake_record(self_inner, activity):
        recorded.append(activity)

    monkeypatch.setattr(Reason, "_record_activity_skills", fake_record)
    monkeypatch.setattr(
        Reason, "generate_response", lambda *a, **kw: "test response"
    )

    reason = Reason(memory=Memory())
    packet = {
        "message": "hello",
        "memory_context": "",
        "tier": 1,
        "current_activity": {
            "type": "conversation",
            "context_key": "default",
            "activity_id": "abc",
            "skill_domains": [],
            "state": {},
        },
    }
    reason.process(packet)
    assert recorded == []


# ---------------------------------------------------------------------------
# Memory wiring tests
# ---------------------------------------------------------------------------

def test_memory_boosts_keywords_from_skill_domains(monkeypatch):
    """Skill domains from current_activity are appended to retrieval keywords."""
    from coordinators.memory import Memory

    captured_keywords = []

    def fake_retrieve(self_inner, keywords, environment="global"):
        captured_keywords.extend(list(keywords))
        return "context"

    monkeypatch.setattr(Memory, "retrieve", fake_retrieve)
    # Stub out attachment ingestion
    monkeypatch.setattr(Memory, "ingest_attachments", lambda *a, **kw: None)

    mem = Memory()
    packet = {
        "keywords": ["opening", "pawn"],
        "current_activity": {
            "type": "game",
            "skill_domains": ["chess"],
            "state": {},
        },
    }
    mem.process(packet)
    assert "chess" in captured_keywords
    # Original keywords preserved
    assert "opening" in captured_keywords
    assert "pawn" in captured_keywords


def test_memory_no_boost_for_empty_skill_domains(monkeypatch):
    """Empty skill_domains list → no keywords added."""
    from coordinators.memory import Memory

    captured = []

    def fake_retrieve(self_inner, keywords, environment="global"):
        captured.extend(list(keywords))
        return ""

    monkeypatch.setattr(Memory, "retrieve", fake_retrieve)
    monkeypatch.setattr(Memory, "ingest_attachments", lambda *a, **kw: None)

    mem = Memory()
    packet = {
        "keywords": ["status"],
        "current_activity": {
            "type": "task",
            "skill_domains": [],
            "state": {},
        },
    }
    mem.process(packet)
    assert captured == ["status"]
```

---

## Tests to run

```
pytest tests/test_activity_model_wiring.py -v
pytest --basetemp .tmp/pytest-tmp -q
```

All existing tests (1040 after Task A) must still pass. The new file adds 9 tests for
a total of 1049.

---

## Security reminder

Do not stage or commit `world_models/config.py`.

---

## Commit instructions

```
git status
# Verify world_models/config.py is NOT staged.

git add coordinators/orientation.py coordinators/hands.py coordinators/reason.py coordinators/memory.py tests/test_activity_model_wiring.py
git commit -m "feat: Activity model Part B — coordinator wiring

- orientation.py: current_activity added to orientation dict;
  _format_orientation_context injects Activity section (type, board
  state, skills) for non-conversation activities
- hands.py: _update_activity_state(); process() patches last_action
  into activity state after successful whitelist execution
- reason.py: _record_activity_skills(); process() auto-calls it for
  game and learning activity types; look-up-or-create Skill node +
  record_skill_practice on each turn
- memory.py: process() appends skill_domains to keyword list before
  retrieve(), boosting domain-relevant memory recall during activities
- 9 new wiring tests (1049 total)"
git push origin main
```
