"""
utils/verify_audit_log.py

Standalone verifier for Gopher-bot's hash-chained audit logs.

Usage (CLI)::

    python -m utils.verify_audit_log logs/audit/coordinator.jsonl

Usage (library)::

    from utils.verify_audit_log import verify_chain
    ok, errors = verify_chain("logs/audit/coordinator.jsonl")

Exit code 0 = chain intact. Exit code 1 = corruption detected.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import NamedTuple

GENESIS_HASH: str = "0" * 64


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


class ChainError(NamedTuple):
    line_number: int          # 1-based line number in the file
    seq: int | None           # entry seq number if parseable, else None
    error_type: str           # "parse_error", "hash_mismatch", "prev_hash_mismatch", "seq_gap"
    detail: str               # human-readable description


def verify_chain(
    path: str | Path,
) -> tuple[bool, list[ChainError]]:
    """
    Verify the hash chain of an audit log file.

    Reads every line and checks:
    1. Each line is valid JSON with the required fields.
    2. Each entry's entry_hash matches a fresh computation over that entry.
    3. Each entry's prev_hash matches the previous entry's entry_hash
       (or GENESIS_HASH for the first entry).
    4. Sequence numbers increase by 1 with no gaps.

    Args:
        path: Path to a JSONL audit log file.

    Returns:
        (is_valid, errors) where errors is a list of ChainError named tuples.
        is_valid is True iff errors is empty.
    """
    path = Path(path)
    errors: list[ChainError] = []
    expected_prev_hash = GENESIS_HASH
    expected_seq = 1

    if not path.exists():
        return True, []           # empty / non-existent log is valid

    with path.open("r", encoding="utf-8") as fh:
        for lineno, raw_line in enumerate(fh, start=1):
            line = raw_line.strip()
            if not line:
                continue          # skip blank lines

            # --- 1. Parse ---------------------------------------------------
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(ChainError(lineno, None, "parse_error", str(exc)))
                continue

            seq = entry.get("seq")

            # --- 2. Sequence gap check --------------------------------------
            if seq != expected_seq:
                errors.append(ChainError(
                    lineno, seq, "seq_gap",
                    f"expected seq {expected_seq}, got {seq!r}",
                ))
                # Update expected_seq so subsequent entries can still be checked.
                if isinstance(seq, int):
                    expected_seq = seq + 1
                else:
                    expected_seq += 1
            else:
                expected_seq += 1

            # --- 3. Recompute entry_hash ------------------------------------
            stored_hash = entry.get("entry_hash", "")
            entry_for_hashing = {**entry, "entry_hash": ""}
            computed_hash = _sha256(_canonical(entry_for_hashing))

            if computed_hash != stored_hash:
                errors.append(ChainError(
                    lineno, seq, "hash_mismatch",
                    f"stored entry_hash {stored_hash!r} != computed {computed_hash!r}",
                ))

            # --- 4. Check prev_hash links to previous entry -----------------
            prev_hash = entry.get("prev_hash", "")
            if prev_hash != expected_prev_hash:
                errors.append(ChainError(
                    lineno, seq, "prev_hash_mismatch",
                    f"expected prev_hash {expected_prev_hash!r}, got {prev_hash!r}",
                ))

            # Advance the chain using the STORED hash (so we can distinguish
            # entry_hash corruption from prev_hash corruption separately).
            expected_prev_hash = stored_hash

    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: python -m utils.verify_audit_log <logfile>", file=sys.stderr)
        return 2

    log_path = argv[1]
    ok, errors = verify_chain(log_path)

    if ok:
        print(f"OK  {log_path} — chain intact")
        return 0

    print(f"FAIL  {log_path} — {len(errors)} error(s):")
    for err in errors:
        print(f"  line {err.line_number} seq={err.seq!r} [{err.error_type}] {err.detail}")
    return 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
