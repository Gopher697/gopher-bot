"""
Inner Defender audit log.

Every activation of any inner defender layer (Dream AUDIT NE spike,
Pattern Monitor drift alert, Mirror-Self confidence drop) is appended
here as a single JSON line. This log is separate from the hash-chained
Hands audit log — it is observational and does not participate in the
chain. It exists so Gopher can audit the defender's history independently
of the main action log.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

INNER_DEFENDER_LOG_PATH = Path("logs/inner_defender.jsonl")


def log_defender_activation(
    layer: str,
    content: str,
    priority: int,
    details: dict[str, Any] | None = None,
    log_path: Path = INNER_DEFENDER_LOG_PATH,
) -> None:
    """
    Append one inner defender activation record to the log.

    Args:
        layer:    Which layer fired — "dream_audit", "pattern_monitor",
                  or "mirror_self".
        content:  The bid content string (same text Reason will see).
        priority: The bid priority (PRIORITY_SAFETY = 1 for NE spikes).
        details:  Optional dict with layer-specific detail fields.
        log_path: Override for testing.
    """
    entry = {
        "timestamp": time.time(),
        "layer": layer,
        "priority": priority,
        "content": content,
        "details": details or {},
    }
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")
    except Exception:
        pass
