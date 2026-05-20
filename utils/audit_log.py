"""
utils/audit_log.py

Append-only hash-chained audit log for Gopher-bot coordinators.

Each log entry is a JSON object written as a single line (JSONL format).
The chain is maintained by including a SHA-256 hash of the previous entry
in every new entry. Tampering with any entry breaks the chain.

Schema per entry:
    {
        "seq":        int,         # monotonically increasing sequence number
        "timestamp":  str,         # ISO-8601 UTC timestamp
        "event_type": str,         # e.g. "hands_action", "hands_blocked"
        "data":       dict,        # event-specific payload
        "prev_hash":  str,         # sha256 hex of previous entry's raw line
                                   # (GENESIS_HASH for the first entry)
        "entry_hash": str          # sha256 hex of this entry with entry_hash=""
    }

GENESIS_HASH is a 64-character hex string of all zeros, used as the
prev_hash of the very first entry in a log file.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GENESIS_HASH: str = "0" * 64


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(obj: dict) -> str:
    """Stable JSON serialisation (sorted keys, no extra whitespace)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


class AuditLog:
    """
    Append-only hash-chained audit log.

    Usage::

        log = AuditLog("logs/audit/coordinator.jsonl")
        log.append("hands_action", {"action": "read_file", "path": "notes.txt"})

    The file is opened for each write and closed immediately, so concurrent
    writers on different processes will interleave entries (which is fine —
    each entry is self-contained). Do NOT share one AuditLog instance across
    threads without external locking.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append(self, event_type: str, data: dict[str, Any]) -> dict:
        """
        Append a new entry to the log. Returns the written entry dict.

        Args:
            event_type: Short identifier for the event (e.g. "hands_action").
            data:       Arbitrary serialisable payload dict.

        Returns:
            The full entry dict as written (including seq, hashes, timestamp).
        """
        prev_hash, seq = self._read_tail()
        timestamp = datetime.now(timezone.utc).isoformat()
        next_seq = seq + 1

        # Build the entry with a placeholder hash so we can compute it.
        entry: dict[str, Any] = {
            "seq": next_seq,
            "timestamp": timestamp,
            "event_type": event_type,
            "data": data,
            "prev_hash": prev_hash,
            "entry_hash": "",          # placeholder — filled in below
        }

        # Compute entry_hash over the entry with entry_hash="".
        entry["entry_hash"] = _sha256(_canonical(entry))

        line = _canonical(entry)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

        return entry

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_tail(self) -> tuple[str, int]:
        """
        Return (prev_hash, last_seq) by reading the last line of the log file.
        If the file doesn't exist or is empty, returns (GENESIS_HASH, 0).
        """
        if not self.path.exists() or self.path.stat().st_size == 0:
            return GENESIS_HASH, 0

        last_line = _last_nonempty_line(self.path)
        if last_line is None:
            return GENESIS_HASH, 0

        try:
            entry = json.loads(last_line)
            return entry["entry_hash"], int(entry["seq"])
        except (json.JSONDecodeError, KeyError, ValueError):
            # Corrupted tail — treat as genesis so the log can continue.
            # The verifier will report the corruption.
            return GENESIS_HASH, 0


def _last_nonempty_line(path: Path) -> str | None:
    """Read the last non-empty line of a file without loading the whole file."""
    with path.open("rb") as fh:
        # Seek to end then scan backwards for the second-to-last newline.
        fh.seek(0, os.SEEK_END)
        end = fh.tell()
        if end == 0:
            return None

        pos = end - 1
        last_line_start = 0
        while pos >= 0:
            fh.seek(pos)
            ch = fh.read(1)
            if ch == b"\n" and pos < end - 1:
                last_line_start = pos + 1
                break
            pos -= 1

        fh.seek(last_line_start)
        raw = fh.read().strip()
        return raw.decode("utf-8") if raw else None
