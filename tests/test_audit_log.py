"""
Non-graph unit tests for the hash-chained audit log.
No Neo4j connection required.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import pytest

from utils.audit_log import GENESIS_HASH, AuditLog, _canonical, _sha256
from utils.verify_audit_log import ChainError, verify_chain


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_log(tmp_path: Path) -> tuple[AuditLog, Path]:
    log_path = tmp_path / "test_audit.jsonl"
    return AuditLog(log_path), log_path


# ---------------------------------------------------------------------------
# AuditLog unit tests
# ---------------------------------------------------------------------------

def test_first_entry_uses_genesis_hash(tmp_path):
    log, path = make_log(tmp_path)
    entry = log.append("test_event", {"key": "value"})
    assert entry["prev_hash"] == GENESIS_HASH


def test_first_entry_seq_is_1(tmp_path):
    log, path = make_log(tmp_path)
    entry = log.append("test_event", {})
    assert entry["seq"] == 1


def test_second_entry_prev_hash_matches_first(tmp_path):
    log, path = make_log(tmp_path)
    first = log.append("event_a", {"x": 1})
    second = log.append("event_b", {"x": 2})
    assert second["prev_hash"] == first["entry_hash"]


def test_seq_increments(tmp_path):
    log, path = make_log(tmp_path)
    for i in range(5):
        entry = log.append("event", {"i": i})
    assert entry["seq"] == 5


def test_entry_hash_is_sha256_of_entry_with_empty_hash_field(tmp_path):
    log, path = make_log(tmp_path)
    entry = log.append("check_hash", {"payload": "abc"})

    # Recompute manually.
    entry_copy = {**entry, "entry_hash": ""}
    expected_hash = _sha256(_canonical(entry_copy))
    assert entry["entry_hash"] == expected_hash


def test_entries_are_written_as_valid_json_lines(tmp_path):
    log, path = make_log(tmp_path)
    log.append("event_a", {"a": 1})
    log.append("event_b", {"b": 2})

    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 2
    for line in lines:
        parsed = json.loads(line)    # must not raise
        assert "entry_hash" in parsed
        assert "prev_hash" in parsed


def test_append_returns_written_entry(tmp_path):
    log, path = make_log(tmp_path)
    entry = log.append("ret_test", {"val": 42})
    assert entry["event_type"] == "ret_test"
    assert entry["data"] == {"val": 42}
    assert len(entry["entry_hash"]) == 64      # SHA-256 hex


def test_fresh_log_instance_reads_tail_correctly(tmp_path):
    """Two separate AuditLog instances on the same file maintain the chain."""
    path = tmp_path / "shared.jsonl"
    log1 = AuditLog(path)
    first = log1.append("write_1", {})

    log2 = AuditLog(path)
    second = log2.append("write_2", {})

    assert second["prev_hash"] == first["entry_hash"]
    assert second["seq"] == 2


def test_empty_file_treated_as_genesis(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.touch()
    log = AuditLog(path)
    entry = log.append("first", {})
    assert entry["prev_hash"] == GENESIS_HASH
    assert entry["seq"] == 1


# ---------------------------------------------------------------------------
# verify_chain tests
# ---------------------------------------------------------------------------

def test_verify_empty_log_is_valid(tmp_path):
    path = tmp_path / "nonexistent.jsonl"
    ok, errors = verify_chain(path)
    assert ok
    assert errors == []


def test_verify_single_entry_valid(tmp_path):
    log, path = make_log(tmp_path)
    log.append("single", {"x": 1})
    ok, errors = verify_chain(path)
    assert ok, errors


def test_verify_multiple_entries_valid(tmp_path):
    log, path = make_log(tmp_path)
    for i in range(10):
        log.append("bulk", {"i": i})
    ok, errors = verify_chain(path)
    assert ok, errors


def test_verify_detects_entry_hash_tampering(tmp_path):
    log, path = make_log(tmp_path)
    log.append("event_a", {"v": 1})
    log.append("event_b", {"v": 2})

    # Tamper with the first entry's entry_hash.
    lines = path.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[0])
    entry["entry_hash"] = "a" * 64     # fake hash
    lines[0] = _canonical(entry)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    ok, errors = verify_chain(path)
    assert not ok
    error_types = [e.error_type for e in errors]
    assert "hash_mismatch" in error_types


def test_verify_detects_prev_hash_break(tmp_path):
    log, path = make_log(tmp_path)
    log.append("event_a", {"v": 1})
    log.append("event_b", {"v": 2})

    # Tamper with the second entry's prev_hash.
    lines = path.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[1])
    entry_hash_backup = entry["entry_hash"]
    entry["prev_hash"] = "b" * 64     # wrong prev hash
    # Recompute entry_hash so that entry itself appears self-consistent —
    # only the linkage is broken.
    entry["entry_hash"] = ""
    entry["entry_hash"] = _sha256(_canonical(entry))
    lines[1] = _canonical(entry)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    ok, errors = verify_chain(path)
    assert not ok
    error_types = [e.error_type for e in errors]
    assert "prev_hash_mismatch" in error_types


def test_verify_detects_deleted_entry(tmp_path):
    log, path = make_log(tmp_path)
    for i in range(3):
        log.append("ev", {"i": i})

    # Delete the second line (seq 2).
    lines = path.read_text(encoding="utf-8").splitlines()
    del lines[1]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    ok, errors = verify_chain(path)
    assert not ok
    # Either a seq_gap or a prev_hash_mismatch should be reported.
    error_types = [e.error_type for e in errors]
    assert any(t in error_types for t in ("seq_gap", "prev_hash_mismatch"))


def test_verify_detects_data_field_tampering(tmp_path):
    log, path = make_log(tmp_path)
    log.append("action", {"target": "notes.txt"})

    # Change the data payload without updating entry_hash.
    lines = path.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[0])
    entry["data"]["target"] = "config.py"     # malicious edit
    lines[0] = _canonical(entry)              # entry_hash NOT updated
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    ok, errors = verify_chain(path)
    assert not ok
    assert any(e.error_type == "hash_mismatch" for e in errors)


def test_chain_error_namedtuple_fields(tmp_path):
    log, path = make_log(tmp_path)
    log.append("ev", {})

    # Corrupt the only entry.
    lines = path.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[0])
    entry["entry_hash"] = "f" * 64
    lines[0] = _canonical(entry)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    ok, errors = verify_chain(path)
    assert not ok
    err = errors[0]
    assert err.line_number == 1
    assert err.seq == 1
    assert err.error_type == "hash_mismatch"
    assert isinstance(err.detail, str)


def test_verify_detects_parse_error(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text("{not-json}\n", encoding="utf-8")

    ok, errors = verify_chain(path)

    assert not ok
    assert errors[0].error_type == "parse_error"
    assert errors[0].line_number == 1


def test_verify_detects_sequence_gap_even_with_valid_hash(tmp_path):
    log, path = make_log(tmp_path)
    first = log.append("event_a", {})

    entry = {
        "seq": 3,
        "timestamp": "2026-05-20T00:00:00+00:00",
        "event_type": "event_c",
        "data": {},
        "prev_hash": first["entry_hash"],
        "entry_hash": "",
    }
    entry["entry_hash"] = _sha256(_canonical(entry))
    with path.open("a", encoding="utf-8") as fh:
        fh.write(_canonical(entry) + "\n")

    ok, errors = verify_chain(path)

    assert not ok
    assert any(e.error_type == "seq_gap" for e in errors)


def test_hands_production_log_uses_audit_log(tmp_path, monkeypatch):
    from coordinators import hands as hands_module
    from coordinators.hands import Hands

    audit_path = tmp_path / "hands_audit.jsonl"

    class TestAuditLog(hands_module.AuditLog):
        def __init__(self, path):
            super().__init__(audit_path)

    monkeypatch.setattr(hands_module, "AuditLog", TestAuditLog)

    hands = Hands()
    hands.process({"action": {"type": "delete_file", "args": {"path": "/tmp/x.txt"}}})

    ok, errors = verify_chain(audit_path)
    assert ok, errors

    lines = audit_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["event_type"] == "blacklist"
    assert entry["data"]["action_type"] == "delete_file"
