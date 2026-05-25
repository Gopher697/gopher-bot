# Codex Task: User-Configurable Model Overrides

## Context

`coordinators/tier_config.py` hardcodes the specific models used at each tier.
Users cannot change which model is used at a given tier without editing Python source.
The fix: read optional override fields from `world_models/config.py` inside
`get_tier_config()`, falling back to the hardcoded defaults when the field is absent
or `None`.

---

## Files to change

### 1. `world_models/config.example.py`

Append the following block at the end of the file, after the existing API key fields:

```python
# ---------------------------------------------------------------------------
# Optional model overrides
# Set any of these to a model name string to override the tier default.
# Leave as None to use the built-in default.
# ---------------------------------------------------------------------------

# TIER_LOCAL defaults: reason="qwen3.5", sensory="qwen2.5-3b-instruct"
TIER_LOCAL_REASON_MODEL: str | None = None
TIER_LOCAL_SENSORY_MODEL: str | None = None

# TIER_STANDARD defaults: reason="claude-sonnet-4-6", sensory="claude-haiku-4-5-20251001"
TIER_STANDARD_REASON_MODEL: str | None = None
TIER_STANDARD_SENSORY_MODEL: str | None = None

# TIER_ENHANCED defaults: reason="claude-opus-4-6", sensory="claude-haiku-4-5-20251001"
TIER_ENHANCED_REASON_MODEL: str | None = None
TIER_ENHANCED_SENSORY_MODEL: str | None = None
```

---

### 2. `coordinators/tier_config.py`

#### 2a. Add `_get_config_override()` helper

Insert this function immediately before the `get_tier_config()` function (after the
`apply_shutdown_cap()` definition is fine, or just before the public helpers section):

```python
def _get_config_override(attr: str, default: str | None) -> str | None:
    """
    Safely read an optional model override from world_models.config.

    Returns *default* if:
    - world_models.config cannot be imported (test environments)
    - the attribute does not exist on the module (older config.py)
    - the attribute is explicitly set to None
    """
    try:
        from world_models import config  # noqa: PLC0415
        value = getattr(config, attr, None)
        return value if isinstance(value, str) and value.strip() else default
    except Exception:
        return default
```

#### 2b. Update `get_tier_config()`

Replace the existing `get_tier_config()` body with:

```python
def get_tier_config(tier: int) -> dict:
    """Return the TierConfig for the given tier as a plain dict.

    Model assignments can be overridden per-tier via optional fields in
    world_models/config.py (e.g. TIER_LOCAL_REASON_MODEL). Any field set to
    None or absent falls back to the hardcoded default.
    """
    try:
        tier_number = int(tier)
    except (TypeError, ValueError):
        tier_number = DEFAULT_TIER

    cfg = asdict(TIERS.get(tier_number, TIERS[DEFAULT_TIER]))

    _override_map: dict[int, tuple[str, str]] = {
        TIER_LOCAL:    ("TIER_LOCAL_REASON_MODEL",    "TIER_LOCAL_SENSORY_MODEL"),
        TIER_STANDARD: ("TIER_STANDARD_REASON_MODEL", "TIER_STANDARD_SENSORY_MODEL"),
        TIER_ENHANCED: ("TIER_ENHANCED_REASON_MODEL", "TIER_ENHANCED_SENSORY_MODEL"),
    }

    if tier_number in _override_map:
        reason_key, sensory_key = _override_map[tier_number]
        reason_override  = _get_config_override(reason_key,  cfg["reason_model"])
        sensory_override = _get_config_override(sensory_key, cfg["sensory_model"])
        cfg["reason_model"]  = reason_override
        cfg["sensory_model"] = sensory_override

    return cfg
```

---

### 3. `tests/test_tier_config_overrides.py` — new file

```python
"""Tests for user-configurable model overrides in tier_config."""
from __future__ import annotations

import importlib
import sys
import types
from unittest.mock import patch

import pytest

import coordinators.tier_config as tc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_config(**kwargs):
    """Return a minimal fake world_models.config module with given attributes."""
    mod = types.ModuleType("world_models.config")
    for k, v in kwargs.items():
        setattr(mod, k, v)
    return mod


# ---------------------------------------------------------------------------
# _get_config_override
# ---------------------------------------------------------------------------

class TestGetConfigOverride:
    def test_returns_default_when_import_fails(self):
        with patch.dict(sys.modules, {"world_models": None, "world_models.config": None}):
            result = tc._get_config_override("TIER_LOCAL_REASON_MODEL", "default-model")
        assert result == "default-model"

    def test_returns_default_when_attr_missing(self):
        fake = _fake_config()
        with patch.dict(sys.modules, {"world_models.config": fake}):
            result = tc._get_config_override("TIER_LOCAL_REASON_MODEL", "default-model")
        assert result == "default-model"

    def test_returns_default_when_attr_is_none(self):
        fake = _fake_config(TIER_LOCAL_REASON_MODEL=None)
        with patch.dict(sys.modules, {"world_models.config": fake}):
            result = tc._get_config_override("TIER_LOCAL_REASON_MODEL", "default-model")
        assert result == "default-model"

    def test_returns_default_when_attr_is_empty_string(self):
        fake = _fake_config(TIER_LOCAL_REASON_MODEL="   ")
        with patch.dict(sys.modules, {"world_models.config": fake}):
            result = tc._get_config_override("TIER_LOCAL_REASON_MODEL", "default-model")
        assert result == "default-model"

    def test_returns_override_when_set(self):
        fake = _fake_config(TIER_LOCAL_REASON_MODEL="my-custom-model")
        with patch.dict(sys.modules, {"world_models.config": fake}):
            result = tc._get_config_override("TIER_LOCAL_REASON_MODEL", "default-model")
        assert result == "my-custom-model"


# ---------------------------------------------------------------------------
# get_tier_config — override application
# ---------------------------------------------------------------------------

class TestGetTierConfigOverrides:
    def _config_with(self, **kwargs):
        fake = _fake_config(**kwargs)
        return patch.dict(sys.modules, {"world_models.config": fake})

    def test_local_reason_override_applied(self):
        with self._config_with(TIER_LOCAL_REASON_MODEL="llama3-custom"):
            cfg = tc.get_tier_config(tc.TIER_LOCAL)
        assert cfg["reason_model"] == "llama3-custom"

    def test_local_sensory_override_applied(self):
        with self._config_with(TIER_LOCAL_SENSORY_MODEL="phi3-mini"):
            cfg = tc.get_tier_config(tc.TIER_LOCAL)
        assert cfg["sensory_model"] == "phi3-mini"

    def test_standard_reason_override_applied(self):
        with self._config_with(TIER_STANDARD_REASON_MODEL="gpt-4o"):
            cfg = tc.get_tier_config(tc.TIER_STANDARD)
        assert cfg["reason_model"] == "gpt-4o"

    def test_enhanced_reason_override_applied(self):
        with self._config_with(TIER_ENHANCED_REASON_MODEL="gpt-4o"):
            cfg = tc.get_tier_config(tc.TIER_ENHANCED)
        assert cfg["reason_model"] == "gpt-4o"

    def test_none_override_uses_default(self):
        with self._config_with(TIER_LOCAL_REASON_MODEL=None):
            cfg = tc.get_tier_config(tc.TIER_LOCAL)
        assert cfg["reason_model"] == "qwen3.5"

    def test_missing_override_uses_default(self):
        with self._config_with():  # no override fields set
            cfg = tc.get_tier_config(tc.TIER_LOCAL)
        assert cfg["reason_model"] == "qwen3.5"
        assert cfg["sensory_model"] == "qwen2.5-3b-instruct"

    def test_deterministic_tier_unaffected(self):
        with self._config_with(TIER_LOCAL_REASON_MODEL="should-not-apply"):
            cfg = tc.get_tier_config(tc.TIER_DETERMINISTIC)
        assert cfg["reason_model"] is None
        assert cfg["sensory_model"] is None

    def test_only_specified_field_overridden(self):
        """Overriding reason_model should not affect sensory_model."""
        with self._config_with(TIER_LOCAL_REASON_MODEL="custom-reason"):
            cfg = tc.get_tier_config(tc.TIER_LOCAL)
        assert cfg["reason_model"] == "custom-reason"
        assert cfg["sensory_model"] == "qwen2.5-3b-instruct"

    def test_invalid_tier_falls_back_to_default_tier(self):
        with self._config_with():
            cfg = tc.get_tier_config(999)
        # Should not raise; returns DEFAULT_TIER config
        assert cfg["reason_model"] is not None
```

---

## Commit

Single commit:

```
git add world_models/config.example.py coordinators/tier_config.py tests/test_tier_config_overrides.py
git commit -m "feat: user-configurable model overrides via config.py"
git push origin main
```

---

## Verification

```
pytest tests/test_tier_config_overrides.py -v
pytest --ignore=tests/test_graph.py --basetemp .tmp/pytest_overrides -v
```

Full suite should pass. Update `docs/BACKLOG.md` test baseline with new count.

---

## Security note

`config.py` is gitignored. The override fields go in `config.example.py` only.
Codex must NOT touch `config.py` directly.
