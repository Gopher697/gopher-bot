# Codex Task: Configurable Embedding Model Override

## Context

`coordinators/embedder.py` hardcodes `EMBEDDING_MODEL = "text-embedding-nomic-embed-text-v1.5@q8_0"`
at line 10. This is the final hardcoded model name in the system after commits 5faadb0
and 8e9b1dd. The same override pattern used throughout should be applied here.

**Important constraint:** The embedding model determines the vector dimensions stored in
Neo4j. Changing this after vectors are already stored will silently break retrieval —
query vectors will have different dimensions than stored vectors. The config comment
must warn about this explicitly. This is NOT a runtime-swappable setting.

---

## Files to change

### 1. `coordinators/embedder.py`

#### 1a. The constant already exists — no change needed to `EMBEDDING_MODEL`

`EMBEDDING_MODEL = "text-embedding-nomic-embed-text-v1.5@q8_0"` stays as-is. It is
the fallback default.

#### 1b. Add `_get_embedding_model()` helper

Add this function immediately before the `Embedder` class definition:

```python
def _get_embedding_model() -> str:
    """
    Return the embedding model name to use.
    Reads EMBEDDING_MODEL from world_models.config if set;
    falls back to the module-level EMBEDDING_MODEL constant.

    WARNING: The embedding model determines Neo4j vector dimensions.
    Changing this after vectors are already stored will break retrieval.
    Only set this at initial setup, before any data is stored.
    """
    try:
        from world_models import config  # noqa: PLC0415
        value = getattr(config, "EMBEDDING_MODEL", None)
        return value if isinstance(value, str) and value.strip() else EMBEDDING_MODEL
    except Exception:
        return EMBEDDING_MODEL
```

#### 1c. Update `Embedder.embed()` to use the helper

In the `embed()` method, replace:

```python
                {
                    "model": EMBEDDING_MODEL,
                    "input": input_data,
                },
```

with:

```python
                {
                    "model": _get_embedding_model(),
                    "input": input_data,
                },
```

---

### 2. `world_models/config.example.py`

Append to the model overrides block, after the TTS fields:

```python
# ---------------------------------------------------------------------------
# Embedding model (LM Studio local call for vector memory)
# ---------------------------------------------------------------------------
# Default: "text-embedding-nomic-embed-text-v1.5@q8_0"
#
# WARNING: This determines the vector dimensions stored in Neo4j.
# Set this ONCE at initial setup, before storing any data.
# Changing it after vectors are stored will silently break memory retrieval.
# If you change it, you must re-index: delete all Observation nodes and
# re-run the migration to rebuild the vector index with the new dimensions.
EMBEDDING_MODEL: str | None = None
```

---

### 3. `tests/test_embedder_override.py` — new file

```python
"""Tests for the configurable embedding model override."""
from __future__ import annotations

import sys
import types
from unittest.mock import patch

import coordinators.embedder as embedder_mod


def _fake_config(**kwargs):
    mod = types.ModuleType("world_models.config")
    for k, v in kwargs.items():
        setattr(mod, k, v)
    return mod


class TestGetEmbeddingModel:
    def test_returns_constant_when_import_fails(self):
        with patch.dict(sys.modules, {"world_models": None, "world_models.config": None}):
            result = embedder_mod._get_embedding_model()
        assert result == embedder_mod.EMBEDDING_MODEL

    def test_returns_constant_when_attr_missing(self):
        fake = _fake_config()
        with patch.dict(sys.modules, {"world_models.config": fake}):
            result = embedder_mod._get_embedding_model()
        assert result == embedder_mod.EMBEDDING_MODEL

    def test_returns_constant_when_attr_is_none(self):
        fake = _fake_config(EMBEDDING_MODEL=None)
        with patch.dict(sys.modules, {"world_models.config": fake}):
            result = embedder_mod._get_embedding_model()
        assert result == embedder_mod.EMBEDDING_MODEL

    def test_returns_constant_when_attr_is_empty_string(self):
        fake = _fake_config(EMBEDDING_MODEL="   ")
        with patch.dict(sys.modules, {"world_models.config": fake}):
            result = embedder_mod._get_embedding_model()
        assert result == embedder_mod.EMBEDDING_MODEL

    def test_returns_override_when_set(self):
        fake = _fake_config(EMBEDDING_MODEL="mxbai-embed-large-v1")
        with patch.dict(sys.modules, {"world_models.config": fake}):
            result = embedder_mod._get_embedding_model()
        assert result == "mxbai-embed-large-v1"

    def test_module_constant_is_expected_default(self):
        assert embedder_mod.EMBEDDING_MODEL == "text-embedding-nomic-embed-text-v1.5@q8_0"
```

---

## Commit

```
git add coordinators/embedder.py world_models/config.example.py tests/test_embedder_override.py
git commit -m "feat: configurable embedding model via config.py — with re-index warning"
git push origin main
```

## Verification

```
pytest tests/test_embedder_override.py -v
pytest --ignore=tests/test_graph.py --basetemp .tmp/pytest_embedder -v
```

Update `docs/BACKLOG.md` test baseline with new count.

## Security note

`config.py` is gitignored. Codex must NOT touch it.

## Completion note

After this commit, every model call in the system is user-configurable via config.py.
The complete inventory from the AVAILABLE_MODELS task table now includes EMBEDDING_MODEL.
