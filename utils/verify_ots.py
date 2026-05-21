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
from __future__ import annotations

import argparse
import pathlib
import sys
import urllib.request


DEFAULT_CALENDAR_BASE_URL = "https://a.pool.opentimestamps.org"


def upgrade_proof(
    hash_hex: str,
    proof_path: "str | pathlib.Path",
    calendar_base_url: str = DEFAULT_CALENDAR_BASE_URL,
    *,
    _urlopen=None,
) -> bool:
    """
    Fetch an upgraded OpenTimestamps receipt and write it to proof_path.

    Returns True only when the calendar returns HTTP 200 with non-empty bytes.
    Pending receipts, network errors, malformed hashes, and file errors return
    False without modifying the existing proof file.
    """
    if len(hash_hex) != 64:
        return False
    try:
        bytes.fromhex(hash_hex)
    except ValueError:
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


def check_proof_file(proof_path: "str | pathlib.Path") -> str:
    """Return 'present' when proof_path exists and is non-empty, else 'not_found'."""
    p = pathlib.Path(proof_path)
    if p.exists() and p.stat().st_size > 0:
        return "present"
    return "not_found"


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m utils.verify_ots",
        description="Check or upgrade an OpenTimestamps proof file.",
    )
    parser.add_argument("proof_path")
    parser.add_argument("hash_hex")
    parser.add_argument("--upgrade", action="store_true")
    parser.add_argument(
        "--calendar-url",
        default=DEFAULT_CALENDAR_BASE_URL,
        help="OTS calendar base URL",
    )

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 2 if int(exc.code or 0) else 0

    proof_path = pathlib.Path(args.proof_path)

    if args.upgrade:
        if upgrade_proof(
            args.hash_hex,
            proof_path,
            calendar_base_url=args.calendar_url,
        ):
            print(f"UPGRADED {proof_path}  (Bitcoin attestation confirmed)")
            return 0
        if check_proof_file(proof_path) == "present":
            print(f"PENDING  {proof_path}  (calendar has not yet confirmed)")
        else:
            print(f"NOT FOUND {proof_path}")
        return 1

    status = check_proof_file(proof_path)
    if status == "present":
        print(f"PRESENT  {proof_path}")
        return 0

    print(f"NOT FOUND {proof_path}")
    return 1


if __name__ == "__main__":
    sys.exit(_main())
