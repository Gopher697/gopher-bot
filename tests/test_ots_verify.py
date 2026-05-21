"""
Pure unit tests for utils.verify_ots.
No network calls; only tmp_path filesystem writes.
"""
from __future__ import annotations

import urllib.error

from utils.verify_ots import check_proof_file, upgrade_proof


class _FakeResponse:
    def __init__(self, data: bytes, status: int = 200):
        self._data = data
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self) -> bytes:
        return self._data


def test_upgrade_proof_success_writes_confirmed_bytes(tmp_path):
    proof_path = tmp_path / "proof.ots"
    confirmed = b"confirmed ots receipt"
    calls = []

    def fake_urlopen(req, timeout):
        calls.append((req.full_url, timeout))
        return _FakeResponse(confirmed, status=200)

    hash_hex = "a" * 64
    result = upgrade_proof(
        hash_hex,
        proof_path,
        calendar_base_url="https://calendar.test",
        _urlopen=fake_urlopen,
    )

    assert result is True
    assert proof_path.read_bytes() == confirmed
    assert calls == [(f"https://calendar.test/timestamp/{hash_hex}", 15)]


def test_upgrade_proof_pending_404_returns_false_and_leaves_file_unchanged(tmp_path):
    proof_path = tmp_path / "pending.ots"
    proof_path.write_bytes(b"pending receipt")

    def fake_urlopen(req, timeout):
        raise urllib.error.HTTPError(
            req.full_url,
            404,
            "not found",
            hdrs=None,
            fp=None,
        )

    result = upgrade_proof("b" * 64, proof_path, _urlopen=fake_urlopen)

    assert result is False
    assert proof_path.read_bytes() == b"pending receipt"


def test_upgrade_proof_network_error_returns_false(tmp_path):
    def fake_urlopen(req, timeout):
        raise OSError("network down")

    result = upgrade_proof("c" * 64, tmp_path / "proof.ots", _urlopen=fake_urlopen)
    assert result is False


def test_upgrade_proof_bad_hash_returns_false_without_network_call(tmp_path):
    called = []

    def fake_urlopen(req, timeout):
        called.append(True)
        return _FakeResponse(b"should not happen")

    result = upgrade_proof("short", tmp_path / "proof.ots", _urlopen=fake_urlopen)

    assert result is False
    assert called == []


def test_check_proof_file_present(tmp_path):
    proof_path = tmp_path / "proof.ots"
    proof_path.write_bytes(b"proof")
    assert check_proof_file(proof_path) == "present"


def test_check_proof_file_absent(tmp_path):
    assert check_proof_file(tmp_path / "missing.ots") == "not_found"


def test_check_proof_file_empty(tmp_path):
    proof_path = tmp_path / "empty.ots"
    proof_path.write_bytes(b"")
    assert check_proof_file(proof_path) == "not_found"
