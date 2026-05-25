# Codex Task: Surface current_time in the orientation context header

## Problem

When a user asks "What time is it?", the bot answers "I don't have access to a real-time
clock." This is wrong. `Awareness.synchronous_run()` already injects `current_time`
(a UTC ISO string) into the packet on every turn. But `_operational_context()` in
`coordinators/orientation.py` never reads it — so it never reaches Reason's context
window, and the model genuinely can't see the clock.

The bot correctly reports process uptime ("up ~10 minutes") because `session_age_seconds`
IS used. `current_time` is simply missing from the same function.

## Change required

**One file, one function, two lines added.**

In `coordinators/orientation.py`, inside `_operational_context(packet, now_ts)`:

Add the current time as the **first** item in `parts`, before the process-uptime entry.

```python
def _operational_context(packet: dict, now_ts: float) -> str:
    """..."""
    parts: list[str] = []

    # Add this block — surface the actual clock time:
    current_time = packet.get("current_time")
    if current_time:
        parts.append(f"Current time: {current_time}")

    session_age = packet.get("session_age_seconds")
    if session_age is not None:
        h = int(session_age) // 3600
        m = (int(session_age) % 3600) // 60
        parts.append(f"Process up {h}h{m}m")

    # ... rest of function unchanged ...
```

That is the entire change. Do not modify anything else in this file.

## Test required

In `tests/test_orientation.py` (or the relevant existing orientation test file),
add one test to the section that covers `_operational_context`:

```
test_operational_context_includes_current_time:
    Call _operational_context with a packet containing current_time="2026-05-25T22:22:00+00:00"
    and reasonable values for the other temporal fields.
    Assert "Current time: 2026-05-25T22:22:00+00:00" is in the returned string.

test_operational_context_omits_current_time_when_absent:
    Call _operational_context with a packet that has no current_time key.
    Assert the returned string does not contain "Current time:".
```

## Acceptance criteria

```
pytest tests/test_orientation.py -v   # new tests pass, no regressions
pytest --basetemp .tmp/pytest-tmp -q  # full suite still passes
```

After implementing: restart the bot, ask "What time is it?", and confirm the reply
includes the actual UTC timestamp rather than deflecting.

## Security reminder

Do not stage or commit `world_models/config.py`. Run `git status` before committing.
