# Codex Task — Add API call timeouts to prevent bot hang

## Context and Why This Matters

The bot got stuck "typing" in Discord for 4+ minutes and never replied. Root cause:
every LM Studio and Anthropic API call in the codebase uses default SDK timeouts.
The OpenAI SDK default is 600 seconds (10 minutes). When LM Studio is in a degraded
state (model mid-load, overloaded, or unavailable), the call blocks indefinitely
instead of failing fast and letting the bot reply via fallback.

The fix: add explicit timeouts to every client instantiation, and wrap each call
site in a timeout-specific except clause that logs and returns a graceful fallback
rather than propagating the exception up to hang the Discord response loop.

**Files that change:**
1. `coordinators/reason.py` — `_call_local_reasoner`, `_call_anthropic_reasoner`
2. `coordinators/sensory.py` — `_call_local_classifier`, `_call_anthropic_classifier`, `_describe_image`
3. `coordinators/archivist.py` — `_extract_claims` (already has a broad try/except; just needs a timeout added to the client)

Do not modify `world_models/config.py` or `world_models/graph.py`.

---

## Security invariant

Run `git status` before committing. If `world_models/config.py` appears, STOP.

---

## Timeout values

```python
REASON_TIMEOUT_SECONDS   = 90    # Qwen3.5 ran in 41s last session; 90s gives headroom
SENSORY_TIMEOUT_SECONDS  = 30    # Classification/description — should be fast
ARCHIVIST_TIMEOUT_SECONDS = 20   # qwen2.5-3b-instruct claim extraction — short text
```

Add these as module-level constants at the top of each file, after the imports.

---

## Part 1 — `coordinators/reason.py`

### Add constants (after imports, before the `Reason` class)

```python
REASON_TIMEOUT_SECONDS = 90
```

### Replace `_call_local_reasoner`

```python
def _call_local_reasoner(
    message: str,
    system_prompt: str,
    tier_config: dict,
    lm_studio_api_key: str | None = None,
) -> Any:
    api_key = (
        lm_studio_api_key
        if lm_studio_api_key is not None
        else config.LM_STUDIO_API_KEY
    )
    client = OpenAI(
        base_url=tier_config["base_url"],
        api_key=api_key,
        timeout=REASON_TIMEOUT_SECONDS,
    )
    return client.chat.completions.create(
        model=tier_config["reason_model"],
        max_tokens=1024,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ],
    )
```

### Replace `_call_anthropic_reasoner`

```python
def _call_anthropic_reasoner(message: str, system_prompt: str, tier_config: dict) -> Any:
    client = Anthropic(
        api_key=config.ANTHROPIC_API_KEY,
        timeout=REASON_TIMEOUT_SECONDS,
    )
    return client.messages.create(
        model=tier_config["reason_model"],
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": message}],
    )
```

### Update `Reason.generate_response()` to catch timeout

The existing `Reason.process()` already wraps `generate_response()` in a try/except
that catches `Exception`. That is sufficient — a timeout will raise an exception,
which will be caught, logged, and set `packet["error"]`. The bot will not hang.

No change needed to `process()`.

---

## Part 2 — `coordinators/sensory.py`

### Add constants (after imports)

```python
SENSORY_TIMEOUT_SECONDS = 30
```

### Find `_call_local_classifier` and add timeout

Locate the function that creates `OpenAI(base_url=tier_config["base_url"], ...)` for
classification. Add `timeout=SENSORY_TIMEOUT_SECONDS` to the constructor:

```python
client = OpenAI(
    base_url=tier_config["base_url"],
    api_key=api_key,
    timeout=SENSORY_TIMEOUT_SECONDS,
)
```

### Find `_call_anthropic_classifier` and add timeout

```python
client = Anthropic(
    api_key=config.ANTHROPIC_API_KEY,
    timeout=SENSORY_TIMEOUT_SECONDS,
)
```

### Find `_describe_image` and add timeout

The `_describe_image` function already has a try/except. Just add the timeout to the
`Anthropic(...)` client instantiation inside it:

```python
client = Anthropic(
    api_key=config.ANTHROPIC_API_KEY,
    timeout=SENSORY_TIMEOUT_SECONDS,
)
```

---

## Part 3 — `coordinators/archivist.py`

### Add constants (after imports)

```python
ARCHIVIST_TIMEOUT_SECONDS = 20
```

### Find `_extract_claims` and add timeout to the OpenAI client

Inside `_extract_claims`, locate:
```python
client = OpenAI(
    base_url="http://localhost:1234/v1",
    api_key="lm-studio",
)
```

Replace with:
```python
client = OpenAI(
    base_url="http://localhost:1234/v1",
    api_key="lm-studio",
    timeout=ARCHIVIST_TIMEOUT_SECONDS,
)
```

The existing `try/except` around this block already handles all exceptions and returns
`[]`. No other change needed.

---

## Part 4 — Tests (`tests/test_api_timeouts.py`)

Create this new test file:

```python
"""Tests confirming timeout values are set on API clients."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest


# ── reason.py timeout constants ──────────────────────────────────────────────

def test_reason_timeout_constant_exists():
    from coordinators.reason import REASON_TIMEOUT_SECONDS
    assert isinstance(REASON_TIMEOUT_SECONDS, (int, float))
    assert REASON_TIMEOUT_SECONDS > 0


def test_call_local_reasoner_passes_timeout():
    """OpenAI client for reason is constructed with timeout=REASON_TIMEOUT_SECONDS."""
    from coordinators.reason import REASON_TIMEOUT_SECONDS
    import coordinators.reason as reason_mod

    created_clients = []

    class FakeOpenAI:
        def __init__(self, **kwargs):
            created_clients.append(kwargs)
            self.chat = MagicMock()
            self.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="ok"))]
            )

    with patch.object(reason_mod, "OpenAI", FakeOpenAI):
        reason_mod._call_local_reasoner(
            "hi", "sys", {"base_url": "http://localhost:1234/v1", "reason_model": "m"}
        )

    assert len(created_clients) == 1
    assert created_clients[0].get("timeout") == REASON_TIMEOUT_SECONDS


def test_call_anthropic_reasoner_passes_timeout():
    """Anthropic client for reason is constructed with timeout=REASON_TIMEOUT_SECONDS."""
    from coordinators.reason import REASON_TIMEOUT_SECONDS
    import coordinators.reason as reason_mod

    created_clients = []

    class FakeAnthropic:
        def __init__(self, **kwargs):
            created_clients.append(kwargs)
            self.messages = MagicMock()
            self.messages.create.return_value = MagicMock(content=[])

        def __call__(self, **kwargs):
            return self

    with patch.object(reason_mod, "Anthropic", FakeAnthropic):
        reason_mod._call_anthropic_reasoner(
            "hi", "sys", {"reason_model": "claude-haiku-4-5-20251001"}
        )

    assert len(created_clients) == 1
    assert created_clients[0].get("timeout") == REASON_TIMEOUT_SECONDS


# ── sensory.py timeout constants ─────────────────────────────────────────────

def test_sensory_timeout_constant_exists():
    from coordinators.sensory import SENSORY_TIMEOUT_SECONDS
    assert isinstance(SENSORY_TIMEOUT_SECONDS, (int, float))
    assert SENSORY_TIMEOUT_SECONDS > 0


# ── archivist.py timeout constants ───────────────────────────────────────────

def test_archivist_timeout_constant_exists():
    from coordinators.archivist import ARCHIVIST_TIMEOUT_SECONDS
    assert isinstance(ARCHIVIST_TIMEOUT_SECONDS, (int, float))
    assert ARCHIVIST_TIMEOUT_SECONDS > 0


# ── Reason.process() survives a timeout exception ────────────────────────────

def test_reason_process_survives_timeout():
    """If generate_response raises (e.g. timeout), process() returns packet with error key."""
    from coordinators.reason import Reason

    reason = Reason()

    def explode(*args, **kwargs):
        raise TimeoutError("LM Studio did not respond in time")

    reason.generate_response = explode
    packet = {"message": "hello", "memory_context": "", "tier": 1}
    result = reason.process(packet)
    assert "error" in result
    assert "reason_output" not in result
```

---

## Verification

```
pytest tests/test_api_timeouts.py -v
pytest --ignore=tests/test_graph.py --basetemp .tmp/pytest_timeouts -v
```

Confirm `world_models/config.py` is not staged:
```
git status
```

Commit:
```
git commit -m "fix: add API call timeouts to prevent bot hang on LM Studio degradation"
```
