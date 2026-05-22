# Codex Task 61 — OpenTimestamps Full Verification + Fix dream.py Dead Code

## Context

Gopher-bot's Dream coordinator already submits a SHA-256 hash of the audit log chain head
to the OpenTimestamps public calendar nightly (`_maybe_anchor_ots` in `coordinators/dream.py`).
The calendar returns a *pending* `.ots` receipt — it commits to anchoring the hash in a
Bitcoin transaction within hours, but the receipt is not confirmed immediately.

Task 61 has two parts:
1. Fix a dead-code bug in `_submit_bid_to_awareness_queue` (dream.py line ~674)
2. Build the full OTS verification workflow: an upgrade function + standalone CLI that checks
   whether a pending receipt has been confirmed on Bitcoin, and saves the upgraded receipt.

Also fixes a path discrepancy: proofs currently save to `logs/dream/ots_proofs/` but
AGENT_COMMITMENTS C-006 criterion (3) specifies `logs/audit/timestamps/`.

---

## Security invariant — check before every commit

`world_models/config.py` is gitignored and contains Neo4j credentials and API keys.
Run `git status` before committing. If `world_models/config.py` appears, STOP — do not commit.

---

## Part 1: Fix dead code in `_submit_bid_to_awareness_queue`

**File:** `coordinators/dream.py`

**Current code (lines ~669-674):**
```python
def _submit_bid_to_awareness_queue(awareness_queue, bid) -> None:
    submit = getattr(awareness_queue, "submit", None)
    if callable(submit):
        submit(bid)
        return
    awareness_queue.put(bid)
```

The `.put()` fallback is dead code. `BidQueue` always has `.submit()` — that is the only
valid submission method in this codebase. The `getattr` dance was defensive programming
for a case that never occurs. If `awareness_queue` lacks `.submit()`, we *want* an
AttributeError to surface rather than silently discarding a coroutine object.

**Replace with:**
```python
def _submit_bid_to_awareness_queue(awareness_queue, bid) -> None:
    awareness_queue.submit(bid)
```

No other changes to the function's callers.

---

## Part 2: Fix OTS proof save path

**File:** `coordinators/dream.py`

**Current constant (line ~58):**
```python
DREAM_LOG_DIR = "logs/dream"
```

**Add a new constant immediately after (or near) the OTS constants:**
```python
# OTS proof files — path must match AGENT_COMMITMENTS C-006 criterion (3).
OTS_PROOF_DIR = "logs/audit/timestamps"
```

**In `_maybe_anchor_ots` (around line ~505-507), change the proof_path construction from:**
```python
proof_path = pathlib.Path(DREAM_LOG_DIR) / "ots_proofs" / f"{date_str}.ots"
```

**To:**
```python
proof_path = pathlib.Path(OTS_PROOF_DIR) / f"{date_str}.ots"
```

Export `OTS_PROOF_DIR` in the module so tests can import it.

---

## Part 3: New `utils/verify_ots.py`

Create a new file: `utils/verify_ots.py`

This module provides:
- `upgrade_proof(hash_hex, proof_path, calendar_base_url)` — checks if a pending receipt
  has been confirmed on Bitcoin by querying the calendar's upgrade endpoint. If confirmed,
  overwrites the pending receipt with the upgraded bytes.
- `check_proof_file(proof_path)` — reports whether a proof file exists on disk.
- CLI: `python -m utils.verify_ots <proof_path> <hash_hex> [--calendar-url URL]`

### How OpenTimestamps upgrade works

When you POST a hash to `https://a.pool.opentimestamps.org/digest`, the calendar returns
a pending receipt (binary `.ots` file). Once the calendar has included the hash in a
Bitcoin transaction, the *upgraded* receipt is available at:

```
GET https://a.pool.opentimestamps.org/timestamp/{hash_hex}
```

- HTTP 200 → receipt has Bitcoin attestation; response body is upgraded `.ots` bytes
- HTTP 404 → still pending; try again later
- Any other error → network issue; leave existing receipt untouched

The upgraded receipt is larger than the pending one (contains the Bitcoin Merkle path).

### `utils/verify_ots.py` implementation

```python
"""
utils/verify_ots.py

OpenTimestamps proof upgrade and status checker for Gopher-bot.

Usage (library)::

    from utils.verify_ots import upgrade_proof, check_proof_file
    upgraded = upgrade_proof("abc123...", "logs/audit/timestamps/2026-05-20.ots")

Usage (CLI)::

    python -m utils.verify_ots logs/audit/timestamps/2026-05-20.ots abc123...
    python -m utils.verify_ots logs/audit/timestamps/2026-05-20.ots abc123... --upgrade

Exit codes: 0 = proof present (or upgraded), 1 = not found / pending / error, 2 = usage error
"""
```

**`upgrade_proof(hash_hex, proof_path, calendar_base_url="https://a.pool.opentimestamps.org") -> bool`**

- `hash_hex`: 64-char hex string (the chain head hash that was submitted)
- `proof_path`: path to the `.ots` file on disk (may or may not exist yet)
- `calendar_base_url`: base URL of the OTS calendar server (injectable for tests)
- Returns `True` if the upgrade succeeded and the file was written; `False` otherwise
- On any exception (network, file I/O, malformed hash), returns `False` silently

Implementation outline:
```python
def upgrade_proof(
    hash_hex: str,
    proof_path: "str | pathlib.Path",
    calendar_base_url: str = "https://a.pool.opentimestamps.org",
    *,
    _urlopen=None,   # injectable for tests
) -> bool:
    import pathlib
    import urllib.request

    if len(hash_hex) != 64:
        return False

    urlopen = _urlopen or urllib.request.urlopen
    url = f"{calendar_base_url.rstrip('/')}/timestamp/{hash_hex}"

    try:
        req = urllib.request.Request(url, method="GET")
        with urlopen(req, timeout=15) as resp:
            if resp.status != 200:
                return False
            data = resp.read()
        if not data:
            return False
        path = pathlib.Path(proof_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return True
    except Exception:
        return False
```

**`check_proof_file(proof_path) -> str`**

Returns:
- `"present"` if the file exists and has non-zero size
- `"not_found"` if the file does not exist or is empty

```python
def check_proof_file(proof_path: "str | pathlib.Path") -> str:
    import pathlib
    p = pathlib.Path(proof_path)
    if p.exists() and p.stat().st_size > 0:
        return "present"
    return "not_found"
```

**CLI (`_main`)**

```
Usage: python -m utils.verify_ots <proof_path> <hash_hex> [--upgrade] [--calendar-url URL]

Without --upgrade: reports whether the proof file is present on disk.
With --upgrade:    attempts to fetch the confirmed receipt from the OTS calendar.
                   If successful, overwrites the pending receipt with the confirmed one.

Exit codes:
  0  proof present (or upgrade succeeded)
  1  not found, still pending, or error
  2  usage error
```

Output examples:
```
PRESENT  logs/audit/timestamps/2026-05-20.ots
UPGRADED logs/audit/timestamps/2026-05-20.ots  (Bitcoin attestation confirmed)
PENDING  logs/audit/timestamps/2026-05-20.ots  (calendar has not yet confirmed)
NOT FOUND logs/audit/timestamps/2026-05-20.ots
```

---

## Part 4: Wire upgrade into Dream's `_maybe_anchor_ots`

After a successful anchor, store the `hash_hex` that was submitted so the upgrade function
can later be called with it. Update `AuditResult` to carry `ots_hash` (the hex submitted),
and update `DreamLog` to record it. This allows a future NREM pass (or the CLI) to upgrade
the receipt.

Add to `AuditResult` dataclass:
```python
ots_hash: str = ""   # chain head hash submitted to OTS calendar this run
```

In `_maybe_anchor_ots`, after a successful anchor:
```python
audit_result.ots_hash = chain_head_hash
```

Update `_save_dream_log` to include `"ots_hash"` in the `"audit"` sub-dict.

---

## Part 5: Tests

### `tests/test_ots_verify.py` (new file)

All tests must be pure Python — no network calls, no disk I/O beyond `tmp_path`.
Use `monkeypatch` or the `_urlopen` injection parameter to mock HTTP.

Required tests:

**`upgrade_proof` — success path**
- Mock `_urlopen` to return HTTP 200 with fake bytes
- Assert function returns `True`
- Assert file was written to `proof_path` with correct bytes

**`upgrade_proof` — pending (404)**
- Mock `_urlopen` to raise `urllib.error.HTTPError` with code 404
- Assert returns `False`
- Assert no file written (or existing file unchanged)

**`upgrade_proof` — network error**
- Mock `_urlopen` to raise `OSError`
- Assert returns `False`

**`upgrade_proof` — bad hash_hex (not 64 chars)**
- Call with `hash_hex="short"`
- Assert returns `False` immediately (no network call)

**`check_proof_file` — file present**
- Write a small file to `tmp_path`
- Assert returns `"present"`

**`check_proof_file` — file absent**
- Assert returns `"not_found"` for a nonexistent path

**`check_proof_file` — empty file**
- Write a zero-byte file
- Assert returns `"not_found"`

### `tests/test_dream_audit.py` — update OTS path tests

The `_maybe_anchor_ots` tests that check `audit.ots_proof_path` must now expect the path
under `OTS_PROOF_DIR` (i.e. `logs/audit/timestamps/YYYY-MM-DD.ots`) instead of
`logs/dream/ots_proofs/`. Import `OTS_PROOF_DIR` from `coordinators.dream` in those tests.

Also add a test that a successful anchor populates `audit_result.ots_hash` with the 64-char
chain head hash.

---

## Verification

Run all three test files and confirm passing:

```
pytest tests/test_dream_audit.py --basetemp .tmp/pytest_codex_task61 -v
pytest tests/test_ots_verify.py --basetemp .tmp/pytest_codex_task61 -v
pytest tests/test_dream_nrem.py --basetemp .tmp/pytest_codex_task61 -v
```

Then run the full test suite to confirm no regressions:

```
pytest --basetemp .tmp/pytest_codex_task61 -v
```

Confirm `world_models/config.py` is NOT staged:
```
git status
```

Commit (single-line message, cmd.exe compatible):
```
git commit -m "feat: OTS upgrade verification + fix dead .put() code (Task 61)"
```

---

## Summary of changes

| File | Change |
|---|---|
| `coordinators/dream.py` | Fix `_submit_bid_to_awareness_queue` — remove dead `.put()` fallback |
| `coordinators/dream.py` | Add `OTS_PROOF_DIR = "logs/audit/timestamps"` constant |
| `coordinators/dream.py` | Fix `_maybe_anchor_ots` proof path to use `OTS_PROOF_DIR` |
| `coordinators/dream.py` | Add `ots_hash: str = ""` to `AuditResult`; populate on successful anchor |
| `coordinators/dream.py` | Update `_save_dream_log` to include `ots_hash` in audit sub-dict |
| `utils/verify_ots.py` | New: `upgrade_proof()`, `check_proof_file()`, CLI |
| `tests/test_ots_verify.py` | New: 7+ unit tests for verify_ots |
| `tests/test_dream_audit.py` | Update OTS path assertions; add `ots_hash` assertion |
