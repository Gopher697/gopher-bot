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
