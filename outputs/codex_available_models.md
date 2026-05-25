# Codex Task: AVAILABLE_MODELS — Intelligent Model Selection (Option B)

## Context

Commit 5faadb0 added per-field model overrides to config.py (11 fields total).
This task replaces that mechanism with a cleaner `AVAILABLE_MODELS` list that lets
users declare what models they have without needing to understand the internal tier
architecture. The tier system picks the best available model for each role at runtime.

The per-field overrides (TIER_LOCAL_REASON_MODEL, etc.) remain in config.example.py
and continue to work as a higher-priority override layer — this is intentional for
power users and backwards compatibility. Priority order:

  1. Per-field config override (e.g. TIER_LOCAL_REASON_MODEL) — highest priority
  2. AVAILABLE_MODELS list — picks best match for role
  3. Hardcoded tier defaults — lowest priority / fallback

---

## Capability vocabulary

Five capability strings. Users annotate each model in AVAILABLE_MODELS with one:

| Capability | Meaning | Example models |
|---|---|---|
| `"capable"` | Heavy reasoning, enhanced tier | claude-opus-*, gpt-4o, llama-3-70b |
| `"standard"` | Solid reasoning, standard tier | claude-sonnet-*, gpt-4o-mini, llama-3-8b |
| `"fast"` | Quick/cheap responses, cloud sensory | claude-haiku-*, gpt-3.5-turbo |
| `"local"` | Local model, general purpose | qwen3.5, mistral-7b, any mid-size local |
| `"local-fast"` | Local model, small/cheap | qwen2.5-3b-*, phi-3-mini, gemma-2b |

Each role maps to a preference order of capabilities (first match wins):

| Role | Preference order |
|---|---|
| TIER_LOCAL reason | `"local"`, `"local-fast"` |
| TIER_LOCAL sensory | `"local-fast"`, `"local"` |
| TIER_STANDARD reason | `"standard"`, `"capable"` |
| TIER_STANDARD sensory | `"fast"`, `"standard"` |
| TIER_ENHANCED reason | `"capable"`, `"standard"` |
| TIER_ENHANCED sensory | `"fast"`, `"standard"` |
| Archivist | `"local-fast"`, `"local"` |
| STT | not applicable (capability field ignored; STT_MODEL override only) |
| TTS | not applicable (capability field ignored; TTS_MODEL/TTS_VOICE override only) |

---

## Files to change

### 1. `world_models/config.example.py`

Add the following block immediately after the existing API key fields and before the
model override fields. The comment explains the relationship to the per-field overrides:

```python
# ---------------------------------------------------------------------------
# AVAILABLE_MODELS — declare what models you have (Option B)
#
# The tier system will automatically select the best model for each role
# from this list based on the capability annotation. If a per-field override
# (e.g. TIER_LOCAL_REASON_MODEL) is also set, the per-field override wins.
#
# Required fields per entry:
#   name       — exact model identifier string used in API calls
#   provider   — one of: "anthropic", "openai", "deepseek", "lm_studio"
#   capability — one of: "capable", "standard", "fast", "local", "local-fast"
#
# Leave as an empty list [] to rely entirely on per-field overrides or defaults.
# ---------------------------------------------------------------------------
AVAILABLE_MODELS: list[dict] = [
    # Examples — uncomment and edit to match your setup:
    # {"name": "claude-opus-4-6",          "provider": "anthropic",  "capability": "capable"},
    # {"name": "claude-sonnet-4-6",         "provider": "anthropic",  "capability": "standard"},
    # {"name": "claude-haiku-4-5-20251001", "provider": "anthropic",  "capability": "fast"},
    # {"name": "qwen3.5",                   "provider": "lm_studio",  "capability": "local"},
    # {"name": "qwen2.5-3b-instruct",       "provider": "lm_studio",  "capability": "local-fast"},
]
```

---

### 2. `coordinators/tier_config.py`

#### 2a. Add capability constants and role→preference mapping

Add this block immediately after the `TIER_NAMES` dict:

```python
# ---------------------------------------------------------------------------
# Capability vocabulary for AVAILABLE_MODELS
# ---------------------------------------------------------------------------

CAPABILITIES = frozenset({"capable", "standard", "fast", "local", "local-fast"})

# Maps (tier, role) → ordered list of preferred capabilities (first match wins).
# role is "reason" or "sensory".
ROLE_CAPABILITY_PREFERENCE: dict[tuple[int, str], list[str]] = {
    (TIER_LOCAL,    "reason"):  ["local",      "local-fast"],
    (TIER_LOCAL,    "sensory"): ["local-fast",  "local"],
    (TIER_STANDARD, "reason"):  ["standard",   "capable"],
    (TIER_STANDARD, "sensory"): ["fast",        "standard"],
    (TIER_ENHANCED, "reason"):  ["capable",    "standard"],
    (TIER_ENHANCED, "sensory"): ["fast",        "standard"],
    # Archivist uses "archivist" role key
    (TIER_LOCAL,    "archivist"): ["local-fast", "local"],
}

# Provider associated with each tier (used to filter AVAILABLE_MODELS candidates).
TIER_PROVIDER: dict[int, str] = {
    TIER_LOCAL:    "lm_studio",
    TIER_STANDARD: "anthropic",
    TIER_ENHANCED: "anthropic",
}
```

#### 2b. Add `_select_from_available()` helper

Add this function immediately before `_get_config_override()`:

```python
def _select_from_available(
    tier: int,
    role: str,
) -> str | None:
    """
    Select a model from AVAILABLE_MODELS for the given tier and role.

    Reads AVAILABLE_MODELS from world_models.config. Returns the first model
    matching the preferred capability order for (tier, role), filtered to the
    expected provider for that tier. Returns None if AVAILABLE_MODELS is empty,
    unset, or no match is found.
    """
    try:
        from world_models import config  # noqa: PLC0415
        available = getattr(config, "AVAILABLE_MODELS", None)
        if not available or not isinstance(available, list):
            return None
    except Exception:
        return None

    expected_provider = TIER_PROVIDER.get(tier)
    preferences = ROLE_CAPABILITY_PREFERENCE.get((tier, role), [])

    # Build a quick lookup: capability -> first model name with that capability
    # filtered to expected provider
    by_capability: dict[str, str] = {}
    for entry in available:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", "").strip()
        provider = entry.get("provider", "").strip()
        capability = entry.get("capability", "").strip()
        if not name or not capability:
            continue
        if expected_provider and provider != expected_provider:
            continue
        if capability not in by_capability:
            by_capability[capability] = name

    for cap in preferences:
        if cap in by_capability:
            return by_capability[cap]

    return None
```

#### 2c. Update `get_tier_config()` to apply AVAILABLE_MODELS before per-field overrides

The priority order is: per-field override > AVAILABLE_MODELS > hardcoded default.
Since `_get_config_override()` already applies per-field overrides, we apply
AVAILABLE_MODELS first (as the base), then let `_get_config_override()` override on top.

Replace the current body of `get_tier_config()` with:

```python
def get_tier_config(tier: int) -> dict:
    """Return the TierConfig for the given tier as a plain dict.

    Model selection priority (highest to lowest):
    1. Per-field config overrides (TIER_LOCAL_REASON_MODEL etc.)
    2. AVAILABLE_MODELS list — picks best match for role + tier
    3. Hardcoded tier defaults
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

        # Step 1: apply AVAILABLE_MODELS (lower priority than per-field overrides)
        reason_from_available  = _select_from_available(tier_number, "reason")
        sensory_from_available = _select_from_available(tier_number, "sensory")
        if reason_from_available:
            cfg["reason_model"] = reason_from_available
        if sensory_from_available:
            cfg["sensory_model"] = sensory_from_available

        # Step 2: apply per-field overrides (highest priority)
        cfg["reason_model"]  = _get_config_override(reason_key,  cfg["reason_model"])
        cfg["sensory_model"] = _get_config_override(sensory_key, cfg["sensory_model"])

    return cfg
```

#### 2d. Add `get_archivist_model_from_available()` public helper

Add this function after `get_tier_config()`. It is called by archivist.py so the
Archivist role also benefits from AVAILABLE_MODELS selection.

```python
def get_archivist_model_from_available() -> str | None:
    """
    Select an Archivist model from AVAILABLE_MODELS.
    Returns None if AVAILABLE_MODELS is unset or no local-fast/local model found.
    """
    return _select_from_available(TIER_LOCAL, "archivist")
```

---

### 3. `coordinators/archivist.py`

Update `_get_archivist_model()` to consult AVAILABLE_MODELS before falling back to
the config field override and then the constant default.

Replace the existing `_get_archivist_model()` body with:

```python
def _get_archivist_model() -> str:
    """
    Return the model name for claim extraction.

    Priority:
    1. ARCHIVIST_MODEL config field override
    2. AVAILABLE_MODELS (local-fast or local capability)
    3. Module-level ARCHIVIST_MODEL constant
    """
    # Per-field override (highest priority)
    try:
        from world_models import config  # noqa: PLC0415
        value = getattr(config, "ARCHIVIST_MODEL", None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    except Exception:
        pass

    # AVAILABLE_MODELS selection
    try:
        from coordinators.tier_config import get_archivist_model_from_available
        selected = get_archivist_model_from_available()
        if selected:
            return selected
    except Exception:
        pass

    return ARCHIVIST_MODEL
```

---

### 4. `tests/test_available_models.py` — new file

```python
"""Tests for AVAILABLE_MODELS intelligent model selection."""
from __future__ import annotations

import sys
import types
from unittest.mock import patch

import pytest

import coordinators.tier_config as tc


def _fake_config(**kwargs):
    mod = types.ModuleType("world_models.config")
    for k, v in kwargs.items():
        setattr(mod, k, v)
    return mod


def _with_config(**kwargs):
    fake = _fake_config(**kwargs)
    return patch.dict(sys.modules, {"world_models.config": fake})


# ---------------------------------------------------------------------------
# _select_from_available
# ---------------------------------------------------------------------------

class TestSelectFromAvailable:
    def test_returns_none_when_available_models_empty(self):
        with _with_config(AVAILABLE_MODELS=[]):
            result = tc._select_from_available(tc.TIER_LOCAL, "reason")
        assert result is None

    def test_returns_none_when_available_models_unset(self):
        with _with_config():
            result = tc._select_from_available(tc.TIER_LOCAL, "reason")
        assert result is None

    def test_selects_local_reason_model(self):
        models = [
            {"name": "qwen3.5",             "provider": "lm_studio", "capability": "local"},
            {"name": "qwen2.5-3b-instruct", "provider": "lm_studio", "capability": "local-fast"},
        ]
        with _with_config(AVAILABLE_MODELS=models):
            result = tc._select_from_available(tc.TIER_LOCAL, "reason")
        assert result == "qwen3.5"

    def test_selects_local_fast_for_sensory(self):
        models = [
            {"name": "qwen3.5",             "provider": "lm_studio", "capability": "local"},
            {"name": "qwen2.5-3b-instruct", "provider": "lm_studio", "capability": "local-fast"},
        ]
        with _with_config(AVAILABLE_MODELS=models):
            result = tc._select_from_available(tc.TIER_LOCAL, "sensory")
        assert result == "qwen2.5-3b-instruct"

    def test_selects_standard_reason_model(self):
        models = [
            {"name": "claude-sonnet-4-6",         "provider": "anthropic", "capability": "standard"},
            {"name": "claude-haiku-4-5-20251001",  "provider": "anthropic", "capability": "fast"},
        ]
        with _with_config(AVAILABLE_MODELS=models):
            result = tc._select_from_available(tc.TIER_STANDARD, "reason")
        assert result == "claude-sonnet-4-6"

    def test_selects_fast_for_standard_sensory(self):
        models = [
            {"name": "claude-sonnet-4-6",        "provider": "anthropic", "capability": "standard"},
            {"name": "claude-haiku-4-5-20251001", "provider": "anthropic", "capability": "fast"},
        ]
        with _with_config(AVAILABLE_MODELS=models):
            result = tc._select_from_available(tc.TIER_STANDARD, "sensory")
        assert result == "claude-haiku-4-5-20251001"

    def test_falls_back_within_preference_order(self):
        # Only "capable" available, no "standard" — should still pick capable for standard reason
        models = [
            {"name": "claude-opus-4-6", "provider": "anthropic", "capability": "capable"},
        ]
        with _with_config(AVAILABLE_MODELS=models):
            result = tc._select_from_available(tc.TIER_STANDARD, "reason")
        assert result == "claude-opus-4-6"

    def test_filters_by_provider(self):
        # lm_studio model should not be selected for standard tier (anthropic)
        models = [
            {"name": "qwen3.5", "provider": "lm_studio", "capability": "standard"},
        ]
        with _with_config(AVAILABLE_MODELS=models):
            result = tc._select_from_available(tc.TIER_STANDARD, "reason")
        assert result is None

    def test_ignores_invalid_entries(self):
        models = [
            "not-a-dict",
            {"name": "",    "provider": "lm_studio", "capability": "local"},
            {"name": None,  "provider": "lm_studio", "capability": "local"},
            {"name": "qwen3.5", "provider": "lm_studio", "capability": "local"},
        ]
        with _with_config(AVAILABLE_MODELS=models):
            result = tc._select_from_available(tc.TIER_LOCAL, "reason")
        assert result == "qwen3.5"

    def test_first_match_wins(self):
        models = [
            {"name": "model-a", "provider": "lm_studio", "capability": "local"},
            {"name": "model-b", "provider": "lm_studio", "capability": "local"},
        ]
        with _with_config(AVAILABLE_MODELS=models):
            result = tc._select_from_available(tc.TIER_LOCAL, "reason")
        assert result == "model-a"


# ---------------------------------------------------------------------------
# get_tier_config — priority order
# ---------------------------------------------------------------------------

class TestGetTierConfigPriority:
    def test_available_models_overrides_hardcoded_default(self):
        models = [
            {"name": "custom-local", "provider": "lm_studio", "capability": "local"},
        ]
        with _with_config(AVAILABLE_MODELS=models):
            cfg = tc.get_tier_config(tc.TIER_LOCAL)
        assert cfg["reason_model"] == "custom-local"

    def test_per_field_override_beats_available_models(self):
        models = [
            {"name": "from-available", "provider": "lm_studio", "capability": "local"},
        ]
        with _with_config(AVAILABLE_MODELS=models, TIER_LOCAL_REASON_MODEL="from-field"):
            cfg = tc.get_tier_config(tc.TIER_LOCAL)
        assert cfg["reason_model"] == "from-field"

    def test_hardcoded_default_used_when_nothing_configured(self):
        with _with_config(AVAILABLE_MODELS=[]):
            cfg = tc.get_tier_config(tc.TIER_LOCAL)
        assert cfg["reason_model"] == "qwen3.5"

    def test_deterministic_tier_unaffected(self):
        models = [
            {"name": "custom-local", "provider": "lm_studio", "capability": "local"},
        ]
        with _with_config(AVAILABLE_MODELS=models):
            cfg = tc.get_tier_config(tc.TIER_DETERMINISTIC)
        assert cfg["reason_model"] is None


# ---------------------------------------------------------------------------
# get_archivist_model_from_available
# ---------------------------------------------------------------------------

class TestGetArchivistModelFromAvailable:
    def test_returns_local_fast_for_archivist(self):
        models = [
            {"name": "qwen2.5-3b-instruct", "provider": "lm_studio", "capability": "local-fast"},
        ]
        with _with_config(AVAILABLE_MODELS=models):
            result = tc.get_archivist_model_from_available()
        assert result == "qwen2.5-3b-instruct"

    def test_returns_none_when_no_local_models(self):
        models = [
            {"name": "claude-sonnet-4-6", "provider": "anthropic", "capability": "standard"},
        ]
        with _with_config(AVAILABLE_MODELS=models):
            result = tc.get_archivist_model_from_available()
        assert result is None
```

---

## Backlog update

Add the following entry to `docs/BACKLOG.md` under a new section
**Phase 2 — Model Intelligence** (create it if it doesn't exist):

```
| ⬜ Model evaluation & advisor | Background coordinator: runs test prompts against AVAILABLE_MODELS on slow cadence, records latency + basic quality signal per role, surfaces recommendations via bid system. Requires hardware probe at startup (VRAM/RAM) for local model viability. Depends on: AVAILABLE_MODELS (this task). |
```

---

## Commit

```
git add world_models/config.example.py coordinators/tier_config.py coordinators/archivist.py tests/test_available_models.py docs/BACKLOG.md
git commit -m "feat: AVAILABLE_MODELS intelligent model selection — tier system picks best fit from user-declared list"
git push origin main
```

## Verification

```
pytest tests/test_available_models.py -v
pytest --ignore=tests/test_graph.py --basetemp .tmp/pytest_available -v
```

Update `docs/BACKLOG.md` test baseline with new count.

## Security note

`config.py` is gitignored. Codex must NOT touch it.
