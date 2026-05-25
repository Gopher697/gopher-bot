# Codex Task: Configurable Model Overrides — Archivist, STT, TTS

## Context

Three remaining hardcoded model names exist after commit 5faadb0:

1. `coordinators/archivist.py` line 89: `model="qwen2.5-3b-instruct"` — LM Studio call
2. `interface/stt.py` line 23: `model="whisper-1"` — OpenAI Whisper transcription
3. `interface/tts.py` line 19: `model="tts-1"` + `voice="fable"` — OpenAI TTS

All three should follow the same override pattern introduced in 5faadb0: module-level
constant as default, safe config.py read, fall back to constant if unset or None.

This is a completeness pass — the goal is that after this commit, every LLM/model call
in the system has a corresponding config.py override field. A future task (Option B)
will replace these individual fields with intelligent model selection from a user-defined
list; this task puts all the knobs in place so Option B has a complete inventory to work
from.

---

## Files to change

### 1. `coordinators/archivist.py`

#### 1a. Add module-level constant

In the constants block at the top (alongside existing `ARCHIVIST_*` constants, after
`ARCHIVIST_TIMEOUT_SECONDS`):

```python
ARCHIVIST_MODEL = "qwen2.5-3b-instruct"
```

#### 1b. Add `_get_archivist_model()` helper

Immediately before `_extract_claims()`:

```python
def _get_archivist_model() -> str:
    """
    Return the model name for claim extraction.
    Reads ARCHIVIST_MODEL from world_models.config if set;
    falls back to the module-level ARCHIVIST_MODEL constant.
    """
    try:
        from world_models import config  # noqa: PLC0415
        value = getattr(config, "ARCHIVIST_MODEL", None)
        return value if isinstance(value, str) and value.strip() else ARCHIVIST_MODEL
    except Exception:
        return ARCHIVIST_MODEL
```

#### 1c. Replace hardcoded model string in `_extract_claims()`

Replace:
```python
            model="qwen2.5-3b-instruct",
```
with:
```python
            model=_get_archivist_model(),
```

Update the docstring on `_extract_claims()`:
```
    Call the local LLM (qwen2.5-3b-instruct via LM Studio) to extract
```
→
```
    Call the local LLM (via LM Studio) to extract
```

---

### 2. `interface/stt.py`

#### 2a. Add module-level constant

After the imports, before the `transcribe()` function:

```python
STT_MODEL = "whisper-1"
```

#### 2b. Add `_get_stt_model()` helper

```python
def _get_stt_model() -> str:
    """
    Return the STT model name.
    Reads STT_MODEL from world_models.config if set;
    falls back to the module-level STT_MODEL constant.
    """
    try:
        value = getattr(config, "STT_MODEL", None)
        return value if isinstance(value, str) and value.strip() else STT_MODEL
    except Exception:
        return STT_MODEL
```

Note: `config` is already imported at module scope in stt.py — no additional import needed.

#### 2c. Replace hardcoded model in `transcribe()`

Replace:
```python
        model="whisper-1",
```
with:
```python
        model=_get_stt_model(),
```

---

### 3. `interface/tts.py`

#### 3a. Add module-level constants

After the imports, before the `speak()` function:

```python
TTS_MODEL = "tts-1"
TTS_VOICE = "fable"
```

#### 3b. Add `_get_tts_model()` and `_get_tts_voice()` helpers

```python
def _get_tts_model() -> str:
    """
    Return the TTS model name.
    Reads TTS_MODEL from world_models.config if set;
    falls back to the module-level TTS_MODEL constant.
    """
    try:
        value = getattr(config, "TTS_MODEL", None)
        return value if isinstance(value, str) and value.strip() else TTS_MODEL
    except Exception:
        return TTS_MODEL


def _get_tts_voice() -> str:
    """
    Return the TTS voice name.
    Reads TTS_VOICE from world_models.config if set;
    falls back to the module-level TTS_VOICE constant.
    """
    try:
        value = getattr(config, "TTS_VOICE", None)
        return value if isinstance(value, str) and value.strip() else TTS_VOICE
    except Exception:
        return TTS_VOICE
```

Note: `config` is already imported at module scope in tts.py — no additional import needed.

#### 3c. Replace hardcoded values in `speak()`

Replace:
```python
        model="tts-1",
        voice="fable",
```
with:
```python
        model=_get_tts_model(),
        voice=_get_tts_voice(),
```

---

### 4. `world_models/config.example.py`

Append to the existing model overrides block (after the TIER_ENHANCED fields):

```python
# ---------------------------------------------------------------------------
# Archivist model (LM Studio local call for claim extraction)
# ---------------------------------------------------------------------------
# Default: "qwen2.5-3b-instruct"
ARCHIVIST_MODEL: str | None = None

# ---------------------------------------------------------------------------
# Speech-to-Text (OpenAI Whisper API)
# ---------------------------------------------------------------------------
# Default: "whisper-1"
STT_MODEL: str | None = None

# ---------------------------------------------------------------------------
# Text-to-Speech (OpenAI TTS API)
# ---------------------------------------------------------------------------
# Default model: "tts-1"
TTS_MODEL: str | None = None
# Default voice: "fable"  — OpenAI options: alloy, echo, fable, onyx, nova, shimmer
TTS_VOICE: str | None = None
```

---

### 5. `tests/test_archivist_stt_tts_overrides.py` — new file

```python
"""Tests for configurable model overrides: Archivist, STT, TTS."""
from __future__ import annotations

import sys
import types
from unittest.mock import patch

import coordinators.archivist as archivist_mod
import interface.stt as stt_mod
import interface.tts as tts_mod


def _fake_config(**kwargs):
    mod = types.ModuleType("world_models.config")
    for k, v in kwargs.items():
        setattr(mod, k, v)
    return mod


# ---------------------------------------------------------------------------
# Archivist
# ---------------------------------------------------------------------------

class TestGetArchivistModel:
    def test_returns_constant_default_when_import_fails(self):
        with patch.dict(sys.modules, {"world_models": None, "world_models.config": None}):
            result = archivist_mod._get_archivist_model()
        assert result == archivist_mod.ARCHIVIST_MODEL

    def test_returns_constant_default_when_attr_missing(self):
        fake = _fake_config()
        with patch.dict(sys.modules, {"world_models.config": fake}):
            result = archivist_mod._get_archivist_model()
        assert result == archivist_mod.ARCHIVIST_MODEL

    def test_returns_constant_default_when_none(self):
        fake = _fake_config(ARCHIVIST_MODEL=None)
        with patch.dict(sys.modules, {"world_models.config": fake}):
            result = archivist_mod._get_archivist_model()
        assert result == archivist_mod.ARCHIVIST_MODEL

    def test_returns_override_when_set(self):
        fake = _fake_config(ARCHIVIST_MODEL="mistral-7b-instruct")
        with patch.dict(sys.modules, {"world_models.config": fake}):
            result = archivist_mod._get_archivist_model()
        assert result == "mistral-7b-instruct"

    def test_module_constant_is_expected_default(self):
        assert archivist_mod.ARCHIVIST_MODEL == "qwen2.5-3b-instruct"


# ---------------------------------------------------------------------------
# STT
# ---------------------------------------------------------------------------

class TestGetSttModel:
    def test_returns_constant_default_when_attr_missing(self):
        result = stt_mod._get_stt_model()
        # config may or may not be present; either way should return a string
        assert isinstance(result, str) and result.strip()

    def test_module_constant_is_expected_default(self):
        assert stt_mod.STT_MODEL == "whisper-1"

    def test_returns_override_when_config_has_value(self, monkeypatch):
        monkeypatch.setattr(stt_mod.config, "STT_MODEL", "whisper-large-v3", raising=False)
        result = stt_mod._get_stt_model()
        assert result == "whisper-large-v3"

    def test_returns_default_when_config_value_is_none(self, monkeypatch):
        monkeypatch.setattr(stt_mod.config, "STT_MODEL", None, raising=False)
        result = stt_mod._get_stt_model()
        assert result == stt_mod.STT_MODEL


# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------

class TestGetTtsModel:
    def test_module_constants_are_expected_defaults(self):
        assert tts_mod.TTS_MODEL == "tts-1"
        assert tts_mod.TTS_VOICE == "fable"

    def test_returns_model_override(self, monkeypatch):
        monkeypatch.setattr(tts_mod.config, "TTS_MODEL", "tts-1-hd", raising=False)
        assert tts_mod._get_tts_model() == "tts-1-hd"

    def test_returns_voice_override(self, monkeypatch):
        monkeypatch.setattr(tts_mod.config, "TTS_VOICE", "nova", raising=False)
        assert tts_mod._get_tts_voice() == "nova"

    def test_returns_model_default_when_none(self, monkeypatch):
        monkeypatch.setattr(tts_mod.config, "TTS_MODEL", None, raising=False)
        assert tts_mod._get_tts_model() == tts_mod.TTS_MODEL

    def test_returns_voice_default_when_none(self, monkeypatch):
        monkeypatch.setattr(tts_mod.config, "TTS_VOICE", None, raising=False)
        assert tts_mod._get_tts_voice() == tts_mod.TTS_VOICE
```

---

## Commit

```
git add coordinators/archivist.py interface/stt.py interface/tts.py world_models/config.example.py tests/test_archivist_stt_tts_overrides.py
git commit -m "feat: configurable model overrides for Archivist, STT, and TTS"
git push origin main
```

## Verification

```
pytest tests/test_archivist_stt_tts_overrides.py -v
pytest --ignore=tests/test_graph.py --basetemp .tmp/pytest_model_overrides -v
```

Update `docs/BACKLOG.md` test baseline with new count.

## Security note

`config.py` is gitignored. Codex must NOT touch it.

## What this completes

After this commit, every model call in the system has a config.py override field:

| Role | Config field | Default |
|---|---|---|
| Local reason | `TIER_LOCAL_REASON_MODEL` | `"qwen3.5"` |
| Local sensory | `TIER_LOCAL_SENSORY_MODEL` | `"qwen2.5-3b-instruct"` |
| Standard reason | `TIER_STANDARD_REASON_MODEL` | `"claude-sonnet-4-6"` |
| Standard sensory | `TIER_STANDARD_SENSORY_MODEL` | `"claude-haiku-4-5-20251001"` |
| Enhanced reason | `TIER_ENHANCED_REASON_MODEL` | `"claude-opus-4-6"` |
| Enhanced sensory | `TIER_ENHANCED_SENSORY_MODEL` | `"claude-haiku-4-5-20251001"` |
| Archivist | `ARCHIVIST_MODEL` | `"qwen2.5-3b-instruct"` |
| VLM | `VISION_VLM_MODEL` | `""` (disabled) |
| STT | `STT_MODEL` | `"whisper-1"` |
| TTS model | `TTS_MODEL` | `"tts-1"` |
| TTS voice | `TTS_VOICE` | `"fable"` |

This table is the complete inventory for the Option B intelligent selection task.
