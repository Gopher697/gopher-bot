from __future__ import annotations

import json
from types import SimpleNamespace

from utils import model_registry


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_load_registry_returns_default_when_missing(tmp_path):
    registry = model_registry.load_registry(tmp_path / "missing.json")

    assert registry["schema_version"] == 1
    assert "anthropic" in registry["providers"]


def test_load_registry_returns_default_on_malformed_json(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text("{bad json", encoding="utf-8")

    registry = model_registry.load_registry(path)

    assert registry["schema_version"] == 1
    assert registry["providers"]["anthropic"]["known_models"] == []


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "registry.json"
    registry = model_registry.load_registry(tmp_path / "missing.json")
    registry["providers"]["anthropic"]["known_models"] = ["claude-test"]

    model_registry.save_registry(registry, path)
    loaded = model_registry.load_registry(path)

    assert loaded["last_updated"]
    assert loaded["providers"]["anthropic"]["known_models"] == ["claude-test"]


def test_check_model_known_true(tmp_path):
    registry = model_registry.load_registry(tmp_path / "missing.json")
    registry["providers"]["anthropic"]["known_models"] = ["claude-test"]

    assert model_registry.check_model_known("anthropic", "claude-test", registry)


def test_check_model_known_false(tmp_path):
    registry = model_registry.load_registry(tmp_path / "missing.json")
    registry["providers"]["anthropic"]["known_models"] = ["claude-test"]

    assert not model_registry.check_model_known("anthropic", "claude-missing", registry)


def test_check_model_known_false_on_bad_provider(tmp_path):
    registry = model_registry.load_registry(tmp_path / "missing.json")

    assert not model_registry.check_model_known("bad-provider", "model", registry)


def test_discover_models_anthropic_shape():
    def fake_http_get(request, timeout=10):
        return FakeResponse(
            {
                "data": [
                    {"id": "claude-test-1"},
                    {"id": "claude-test-2"},
                ]
            }
        )

    models = model_registry.discover_models(
        "anthropic",
        api_key="test-key",
        http_get_fn=fake_http_get,
    )

    assert models == ["claude-test-1", "claude-test-2"]


def test_discover_models_returns_empty_on_error():
    def fake_http_get(request, timeout=10):
        raise OSError("network down")

    assert model_registry.discover_models("anthropic", http_get_fn=fake_http_get) == []


def test_update_registry_adds_new_models(tmp_path):
    path = tmp_path / "registry.json"
    registry = model_registry.load_registry(tmp_path / "missing.json")
    model_registry.save_registry(registry, path)

    updated = model_registry.update_registry_for_provider(
        "anthropic",
        path=path,
        discover_fn=lambda provider, api_key: ["claude-new"],
    )

    assert "claude-new" in updated["providers"]["anthropic"]["known_models"]


def test_update_registry_moves_removed_model_to_unavailable(tmp_path):
    path = tmp_path / "registry.json"
    registry = model_registry.load_registry(tmp_path / "missing.json")
    registry["providers"]["anthropic"]["known_models"] = ["claude-old", "claude-keep"]
    model_registry.save_registry(registry, path)

    updated = model_registry.update_registry_for_provider(
        "anthropic",
        path=path,
        discover_fn=lambda provider, api_key: ["claude-keep"],
    )

    provider = updated["providers"]["anthropic"]
    assert "claude-old" not in provider["known_models"]
    assert "claude-old" in provider["unavailable_models"]
    assert "claude-keep" in provider["known_models"]


def test_get_configured_models_not_in_registry(tmp_path):
    registry = model_registry.load_registry(tmp_path / "missing.json")
    registry["providers"]["anthropic"]["known_models"] = ["claude-known"]
    fake_tiers = {
        1: SimpleNamespace(
            provider="anthropic",
            sensory_provider=None,
            reason_provider=None,
            sensory_model="claude-missing",
            reason_model=None,
            sensory_fallbacks=[],
            reason_fallbacks=[],
        )
    }

    missing = model_registry.get_configured_models_not_in_registry(
        registry,
        tiers=fake_tiers,
    )

    assert missing == [("anthropic", "claude-missing")]
