"""
utils/model_registry.py - Model availability registry for gopher-bot.

Maintains a local JSON record of known models per provider, discovered by
querying provider API endpoints. No model switching logic lives here; this
module only reads, writes, and queries the registry file. Decisions about
which model to use remain in tier_config.py and the model client layer.

Usage:
from utils.model_registry import load_registry, discover_models, check_model_known
"""

from __future__ import annotations

import copy
import json
import logging
import sys
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from coordinators.tier_config import KNOWN_PROVIDERS, TIERS


logger = logging.getLogger(__name__)

REGISTRY_PATH = PROJECT_ROOT / "world_models" / "model_registry.json"
SCHEMA_VERSION = 1

HttpGetFn = Callable[..., Any]
DiscoverFn = Callable[[str, str | None], list[str]]


def _provider_default() -> dict:
    return {
        "last_discovered": None,
        "known_models": [],
        "unavailable_models": [],
        "discovery_error": None,
    }


def _default_registry() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "last_updated": None,
        "providers": {
            provider: _provider_default()
            for provider in KNOWN_PROVIDERS
        },
    }


def _normalize_registry(registry: dict) -> dict:
    normalized = copy.deepcopy(_default_registry())
    if not isinstance(registry, dict):
        return normalized

    normalized["schema_version"] = registry.get("schema_version", SCHEMA_VERSION)
    normalized["last_updated"] = registry.get("last_updated")

    providers = registry.get("providers", {})
    if not isinstance(providers, dict):
        return normalized

    for provider in KNOWN_PROVIDERS:
        provider_data = providers.get(provider, {})
        if not isinstance(provider_data, dict):
            continue
        normalized["providers"][provider].update(
            {
                "last_discovered": provider_data.get("last_discovered"),
                "known_models": list(provider_data.get("known_models") or []),
                "unavailable_models": list(
                    provider_data.get("unavailable_models") or []
                ),
                "discovery_error": provider_data.get("discovery_error"),
            }
        )
    return normalized


def load_registry(path: Path = REGISTRY_PATH) -> dict:
    try:
        registry = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return _default_registry()
    return _normalize_registry(registry)


def save_registry(registry: dict, path: Path = REGISTRY_PATH) -> None:
    normalized = _normalize_registry(registry)
    normalized["last_updated"] = date.today().isoformat()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(normalized, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def check_model_known(
    provider: str,
    model_id: str,
    registry: dict | None = None,
) -> bool:
    try:
        data = registry if registry is not None else load_registry()
        known_models = data["providers"][provider]["known_models"]
        return model_id in known_models
    except Exception:
        return False


def discover_models(
    provider: str,
    api_key: str | None = None,
    timeout: int = 10,
    http_get_fn: HttpGetFn | None = None,
) -> list[str]:
    models, error = _discover_models_with_error(
        provider,
        api_key=api_key,
        timeout=timeout,
        http_get_fn=http_get_fn,
    )
    if error:
        logger.debug("model discovery failed for %s: %s", provider, error)
    return models


def update_registry_for_provider(
    provider: str,
    api_key: str | None = None,
    path: Path = REGISTRY_PATH,
    discover_fn: DiscoverFn | None = None,
) -> dict:
    registry = load_registry(path)
    if provider not in registry["providers"]:
        return registry

    provider_entry = registry["providers"][provider]
    today = date.today().isoformat()

    if discover_fn is not None:
        try:
            discovered_models = discover_fn(provider, api_key)
            error = None
        except Exception as exc:
            discovered_models = []
            error = str(exc)
    else:
        discovered_models, error = _discover_models_with_error(
            provider,
            api_key=api_key,
        )

    provider_entry["last_discovered"] = today
    if error:
        provider_entry["discovery_error"] = error
        save_registry(registry, path)
        return registry

    discovered = set(discovered_models)
    known = set(provider_entry.get("known_models") or [])
    unavailable = set(provider_entry.get("unavailable_models") or [])

    removed = known - discovered
    known = (known | discovered) - removed
    unavailable = (unavailable | removed) - discovered

    provider_entry["known_models"] = sorted(known)
    provider_entry["unavailable_models"] = sorted(unavailable)
    provider_entry["discovery_error"] = None
    save_registry(registry, path)
    return registry


def get_configured_models_not_in_registry(
    registry: dict | None = None,
    tiers: dict[int, Any] | None = None,
) -> list[tuple[str, str]]:
    data = registry if registry is not None else load_registry()
    try:
        providers = data["providers"]
    except Exception:
        return []

    if not any(entry.get("known_models") for entry in providers.values()):
        return []

    missing: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for provider, model_id in get_configured_models(tiers):
        known = providers.get(provider, {}).get("known_models", [])
        pair = (provider, model_id)
        if model_id not in known and pair not in seen:
            missing.append(pair)
            seen.add(pair)
    return missing


def get_configured_models(tiers: dict[int, Any] | None = None) -> list[tuple[str, str]]:
    configured: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for pair in _configured_models(tiers or TIERS):
        if pair not in seen:
            configured.append(pair)
            seen.add(pair)
    return configured


def _configured_models(tiers: dict[int, Any]) -> list[tuple[str, str]]:
    configured: list[tuple[str, str]] = []
    for tier in tiers.values():
        tier_provider = getattr(tier, "provider", "anthropic")
        sensory_provider = getattr(tier, "sensory_provider", None) or tier_provider
        reason_provider = getattr(tier, "reason_provider", None) or tier_provider

        _append_model(configured, sensory_provider, getattr(tier, "sensory_model", None))
        for model_id in getattr(tier, "sensory_fallbacks", []) or []:
            _append_model(configured, sensory_provider, model_id)

        _append_model(configured, reason_provider, getattr(tier, "reason_model", None))
        for model_id in getattr(tier, "reason_fallbacks", []) or []:
            _append_model(configured, reason_provider, model_id)

    return configured


def _append_model(
    configured: list[tuple[str, str]],
    provider: str,
    model_id: str | None,
) -> None:
    if model_id:
        configured.append((provider, model_id))


def _discover_models_with_error(
    provider: str,
    api_key: str | None = None,
    timeout: int = 10,
    http_get_fn: HttpGetFn | None = None,
) -> tuple[list[str], str | None]:
    provider_info = KNOWN_PROVIDERS.get(provider)
    if provider_info is None:
        return [], f"unknown provider: {provider}"

    http_get = http_get_fn or urllib.request.urlopen
    request = _build_request(provider, provider_info, api_key)

    try:
        try:
            response = http_get(request, timeout=timeout)
        except TypeError:
            response = http_get(request)
        payload = _read_json_response(response)
        models = [
            item.get("id")
            for item in payload.get("data", [])
            if isinstance(item, dict) and item.get("id")
        ]
        return [str(model_id) for model_id in models], None
    except Exception as exc:
        return [], str(exc)


def _build_request(provider: str, provider_info: dict, api_key: str | None):
    headers = {}
    auth_header = provider_info.get("auth_header")
    if auth_header and api_key:
        auth_prefix = provider_info.get("auth_prefix", "")
        headers[auth_header] = f"{auth_prefix}{api_key}"
    if provider == "anthropic":
        headers["anthropic-version"] = "2023-06-01"
    return urllib.request.Request(provider_info["models_endpoint"], headers=headers)


def _read_json_response(response: Any) -> dict:
    if hasattr(response, "__enter__"):
        with response as opened:
            raw = opened.read()
    else:
        raw = response.read()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    payload = json.loads(raw)
    return payload if isinstance(payload, dict) else {}


def _api_key_for_provider(provider: str) -> str | None:
    provider_info = KNOWN_PROVIDERS.get(provider)
    if provider_info is None:
        return None
    try:
        from world_models import config
    except Exception:
        return None
    value = getattr(config, provider_info.get("config_key", ""), None)
    return str(value) if value else None


def _discover_provider_for_cli(provider: str, path: Path = REGISTRY_PATH) -> None:
    before = load_registry(path)
    before_entry = before.get("providers", {}).get(provider, _provider_default())
    before_known = set(before_entry.get("known_models") or [])
    before_unavailable = set(before_entry.get("unavailable_models") or [])

    api_key = _api_key_for_provider(provider)
    discovered_models, error = _discover_models_with_error(provider, api_key=api_key)

    def injected_discover(_provider: str, _api_key: str | None) -> list[str]:
        if error:
            raise RuntimeError(error)
        return discovered_models

    updated = update_registry_for_provider(
        provider,
        api_key=api_key,
        path=path,
        discover_fn=injected_discover,
    )
    updated_entry = updated.get("providers", {}).get(provider, _provider_default())
    after_known = set(updated_entry.get("known_models") or [])
    after_unavailable = set(updated_entry.get("unavailable_models") or [])
    new_count = len(after_known - before_known)
    moved_count = len(after_unavailable - before_unavailable)
    error_status = updated_entry.get("discovery_error") or "none"
    print(
        f"{provider}: found={len(discovered_models)} "
        f"new={new_count} moved_unavailable={moved_count} error={error_status}"
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Gopher-bot model registry tool")
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Query all configured providers and update registry",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default=None,
        help="Limit discovery to one provider",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Print registry contents",
    )
    args = parser.parse_args()

    if args.discover:
        providers = [args.provider] if args.provider else list(KNOWN_PROVIDERS)
        for provider in providers:
            _discover_provider_for_cli(provider)

    if args.show:
        print(json.dumps(load_registry(), indent=2, sort_keys=True))

    if not args.discover and not args.show:
        parser.print_help()


if __name__ == "__main__":
    main()
