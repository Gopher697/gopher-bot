# Codex Task: Local timezone display in Orientation

Small targeted fix. The bot currently shows `Current time: <UTC ISO string>` in its
operational context. The user is in the Eastern US (EDT/EST depending on DST) and the
bot consistently fails to convert correctly when reasoning about local time, sometimes
using the wrong DST offset. Fix: show local time directly so the bot never has to
convert mentally.

---

## Changes required

### 1. `world_models/config.example.py` — add timezone setting

Add at the end of the file, after `EMBEDDING_MODEL`:

```python
# ---------------------------------------------------------------------------
# User timezone (IANA timezone name)
# Used by Orientation to display local time alongside UTC.
# Examples: "America/New_York", "America/Chicago", "America/Los_Angeles",
#           "Europe/London", "Asia/Tokyo"
# Default: "UTC" (no conversion)
# ---------------------------------------------------------------------------
USER_TIMEZONE: str = "UTC"
```

### 2. `world_models/config.py` — add the same setting

The user's `config.py` (gitignored, not committed) needs the same entry added.
Since `config.py` is gitignored, **do not touch it in this task**. Instead,
add a comment in `config_utils.py` or the startup healthcheck noting that
`USER_TIMEZONE` is a new optional config field with default `"UTC"`.

Add a safe fallback import in `coordinators/orientation.py` (see step 3):
```python
try:
    from world_models.config import USER_TIMEZONE as _USER_TIMEZONE
except ImportError:
    _USER_TIMEZONE = "UTC"
```

### 3. `coordinators/orientation.py` — show local time

At the top of the file, add the import (already has `import time` etc.):

```python
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
```

In `_operational_context()`, replace the current time block:

```python
# BEFORE:
current_time = packet.get("current_time")
if current_time:
    parts.append(f"Current time: {current_time}")
```

```python
# AFTER:
current_time = packet.get("current_time")
if current_time:
    parts.append(f"Current time (UTC): {current_time}")
    try:
        tz = ZoneInfo(_USER_TIMEZONE)
        import datetime as _dt
        # current_time is an ISO string; parse it and convert
        utc_dt = _dt.datetime.fromisoformat(current_time.replace("Z", "+00:00"))
        local_dt = utc_dt.astimezone(tz)
        # Format: "Mon 2026-05-26 21:00 EDT" — unambiguous, includes day and tz name
        local_str = local_dt.strftime("%a %Y-%m-%d %H:%M %Z")
        parts.append(f"Local time: {local_str}")
    except (ZoneInfoNotFoundError, ValueError, AttributeError):
        pass  # graceful degradation — UTC only if timezone invalid or time unparseable
```

The bot now sees both:
```
Current time (UTC): 2026-05-26T01:00:00
Local time: Mon 2026-05-26 21:00 EDT
```

And defaults to speaking in local time rather than doing mental timezone arithmetic.

---

## Tests

Add to `tests/test_orientation.py` (or create `tests/test_orientation_timezone.py`):

1. **UTC fallback**: `_USER_TIMEZONE = "UTC"` → local time shown as UTC with no offset.

2. **Valid timezone**: patch `_USER_TIMEZONE = "America/New_York"` → local time string
   contains a valid Eastern timezone abbreviation (`EDT` or `EST` depending on date).

3. **Invalid timezone**: patch `_USER_TIMEZONE = "Invalid/Zone"` → no crash; UTC line
   still present, no local time line (graceful degradation).

4. **Missing current_time**: `packet["current_time"]` not set → no crash; neither
   UTC nor local time lines appear.

5. **DST correctness**: use a known summer date (e.g. `2026-07-01T18:00:00Z`) and
   `America/New_York` → local time shows `14:00 EDT` (UTC-4). Use a known winter date
   (`2026-01-01T18:00:00Z`) → local time shows `13:00 EST` (UTC-5). Verifies DST is
   handled by `zoneinfo`, not manually.

---

## Security reminder

Do not stage or commit `world_models/config.py`.

---

## Commit instructions

```
git status
# Verify world_models/config.py is NOT staged.

git add world_models/config.example.py coordinators/orientation.py tests/test_orientation_timezone.py
git commit -m "fix: show local timezone in Orientation operational context

- config.example.py: USER_TIMEZONE setting (IANA timezone name, default UTC)
- orientation.py: _operational_context() now shows both UTC and local time
- DST handled automatically via zoneinfo
- graceful degradation if timezone invalid or time unparseable
- N new tests"
git push origin main
```

## Note for Gopher

After Codex commits this, open `world_models/config.py` and add:
```python
USER_TIMEZONE: str = "America/New_York"
```
This does not require a bot restart if the bot reads config at import time —
but a restart ensures it takes effect cleanly.
