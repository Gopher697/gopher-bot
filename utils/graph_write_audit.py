"""
Graph write audit logger.

Appends a JSONL entry to logs/graph_writes/YYYYMMDD.jsonl for every
significant coordinator-originated Neo4j write. Provides visibility
into what the graph layer is doing without blocking any operations.

Phase 2 will extend this with a policy layer that gates writes above
the Claim level through the proposal mechanism.
"""
from __future__ import annotations

import json
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SENSITIVE_KEY_PARTS = ("key", "password", "token", "secret")


class ProposalRequiredError(Exception):
    """Raised when a graph write requires a proposal rather than a direct mutation."""


def check_write_policy(node_label: str, action: str) -> None:
    """
    Phase 2 policy gate - currently a no-op.

    Future: raise ProposalRequiredError for Principle/Doctrine direct writes.
    """
    pass


def _default_log_dir() -> Path:
    return PROJECT_ROOT / "logs" / "graph_writes"


def _default_write(path: Path, line: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)


def _safe_properties(properties: dict | None) -> dict:
    if not properties:
        return {}

    safe = {}
    for key, value in properties.items():
        key_text = str(key)
        key_lower = key_text.lower()
        if any(part in key_lower for part in SENSITIVE_KEY_PARTS):
            continue
        safe[key_text] = value
    return safe


def audit_graph_write(
    action: str,
    node_label: str,
    coordinator: str = "unknown",
    properties: dict | None = None,
    log_dir_fn: Callable[[], Path] | None = None,
    write_fn: Callable[[Path, str], None] | None = None,
) -> None:
    """
    Append a structured audit entry to logs/graph_writes/YYYYMMDD.jsonl.

    Never raises - log failures are caught and printed to stderr only.
    """
    try:
        now = datetime.now(timezone.utc)
        log_dir = Path(log_dir_fn() if log_dir_fn else _default_log_dir())
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / f"{now.strftime('%Y%m%d')}.jsonl"
        entry: dict[str, Any] = {
            "ts": now.isoformat().replace("+00:00", "Z"),
            "action": str(action),
            "node_label": str(node_label),
            "coordinator": str(coordinator),
            "properties": _safe_properties(properties),
        }
        line = json.dumps(entry, sort_keys=True, default=str) + "\n"
        writer = write_fn or _default_write
        writer(path, line)
    except Exception as exc:
        print(f"WARNING: graph write audit failed: {exc}", file=sys.stderr)
