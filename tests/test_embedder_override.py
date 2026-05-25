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
