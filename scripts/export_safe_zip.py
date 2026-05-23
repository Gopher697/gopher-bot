"""
export_safe_zip.py — Create a shareable zip of the gopher-bot project.

Excludes all secrets, credentials, runtime state, build artifacts, caches,
and large binaries. Safe to share with reviewers, AI coding agents, or for backup.

Usage:
    python scripts/export_safe_zip.py
    python scripts/export_safe_zip.py --output my-review.zip
    python scripts/export_safe_zip.py --dry-run        # list files without zipping
    python scripts/export_safe_zip.py --verify         # run exclusion checks only
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
import zipfile
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Repo root
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / f"gopher-bot-export-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"

# ---------------------------------------------------------------------------
# Exclusion rules
# ---------------------------------------------------------------------------

# Files/paths that must NEVER appear in an export under any circumstances.
# These are checked against the full relative path (forward-slash, lowercase).
SECRET_PATTERNS: list[str] = [
    "world_models/config.py",
    ".env",
    ".env.*",
    "*.env",
    "id_rsa",
    "id_rsa.pub",
    "id_ed25519",
    "id_ed25519.pub",
    "credentials.json",
    "service_account*.json",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
]

# Directory prefixes that are excluded wholesale (relative, forward-slash).
EXCLUDED_DIR_PREFIXES: list[str] = [
    ".git/",
    ".venv/",
    ".godot/",
    "avatar/.godot/",
    "__pycache__/",
    ".pytest_cache/",
    "pytest_tmp/",
    "test_workspaces/",
    "node_modules/",
    "gopher-brain-data/",
    "logs/actions/",
    "logs/archivist/",
    "logs/audit/",
    "logs/build/",
    "logs/dream/",
    "logs/graph_writes/",
    "logs/pattern_observations/",
    "logs/wisdom/",
]

# Glob patterns matched against the filename only (not the full path).
EXCLUDED_FILENAME_PATTERNS: list[str] = [
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "*.egg-info",
    "*.exe",
    "*.pck",
    "*.dll",
    "*.so",
    "*.dylib",
    "*.zip",
    "*.tar.gz",
    "*.log",
    "index.lock",
    "HEAD.lock",
    "*.uid",
    "*.vulkan.cache",
    "*.res",
    "*.cfg.bak",
    "uid_cache.bin",
    "filesystem_cache*",
    "filesystem_update*",
]

# Glob patterns matched against the full relative path.
EXCLUDED_PATH_PATTERNS: list[str] = [
    "pytest-cache-files-*/",
    "avatar/export/*",
    "avatar/gopher-bot-avatar.console.exe",
    "outputs/screenshots/*",
    "logs/pattern_monitor.jsonl",
    "notes/sessions/*",
    "world_models/neuromodulation_state.json",
    "config/projects.yaml",
    "config/allowed_commands.yaml",
]

# Max file size in bytes — files larger than this are excluded with a warning.
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _rel(path: Path) -> str:
    """Return forward-slash relative path string."""
    return path.relative_to(REPO_ROOT).as_posix()


def _is_secret(rel_path: str) -> bool:
    """Return True if the file matches any secret pattern."""
    rel_lower = rel_path.lower()
    name = rel_path.split("/")[-1].lower()
    for pattern in SECRET_PATTERNS:
        if fnmatch.fnmatch(rel_lower, pattern.lower()):
            return True
        if fnmatch.fnmatch(name, pattern.lower()):
            return True
    return False


def _is_excluded(rel_path: str) -> tuple[bool, str]:
    """
    Return (excluded, reason) for a given relative path.
    Checks are in priority order: secrets first, then dirs, then patterns.
    """
    # 1. Secret check — always highest priority
    if _is_secret(rel_path):
        return True, "SECRET"

    # 2. Directory prefix exclusions
    for prefix in EXCLUDED_DIR_PREFIXES:
        if rel_path.startswith(prefix) or f"/{prefix.rstrip('/')}" in rel_path:
            return True, f"excluded dir ({prefix.rstrip('/')})"

    # 3. Filename pattern exclusions
    name = rel_path.split("/")[-1]
    for pattern in EXCLUDED_FILENAME_PATTERNS:
        if fnmatch.fnmatch(name, pattern):
            return True, f"excluded filename ({pattern})"

    # 4. Full-path pattern exclusions
    for pattern in EXCLUDED_PATH_PATTERNS:
        if fnmatch.fnmatch(rel_path, pattern):
            return True, f"excluded path ({pattern})"

    return False, ""


def collect_files(verbose: bool = False) -> tuple[list[Path], list[tuple[str, str]]]:
    """
    Walk the repo and return (included_files, excluded_list).
    excluded_list entries are (rel_path, reason).
    """
    included: list[Path] = []
    excluded: list[tuple[str, str]] = []

    for path in sorted(REPO_ROOT.rglob("*")):
        if not path.is_file():
            continue

        rel = _rel(path)
        is_ex, reason = _is_excluded(rel)

        if is_ex:
            excluded.append((rel, reason))
            if verbose:
                print(f"  SKIP  [{reason}]  {rel}")
            continue

        if path.stat().st_size > MAX_FILE_SIZE:
            reason = f"too large ({path.stat().st_size // 1024}KB > {MAX_FILE_SIZE // 1024}KB)"
            excluded.append((rel, reason))
            if verbose:
                print(f"  SKIP  [{reason}]  {rel}")
            continue

        included.append(path)

    return included, excluded


def verify_exclusions() -> bool:
    """
    Run exclusion checks against known secret-bearing filenames.
    Returns True if all checks pass (nothing that should be excluded slips through).
    """
    MUST_EXCLUDE = [
        "world_models/config.py",
        ".env",
        "id_rsa",
        "id_ed25519",
        "credentials.json",
    ]

    print("Running exclusion verification...")
    all_passed = True
    for path_str in MUST_EXCLUDE:
        excluded, reason = _is_excluded(path_str)
        status = "PASS" if excluded else "FAIL"
        if not excluded:
            all_passed = False
        print(f"  {status}  {path_str}  →  {'excluded: ' + reason if excluded else 'NOT EXCLUDED — FIX THIS'}")

    if all_passed:
        print("\nAll exclusion checks passed. Safe to export.")
    else:
        print("\nSome checks FAILED. Do not export until fixed.")

    return all_passed


def build_zip(output: Path, dry_run: bool = False) -> None:
    """Collect files and write the zip (or just print if dry_run)."""
    print(f"Repo root: {REPO_ROOT}")
    print(f"Output:    {output if not dry_run else '(dry run — no file written)'}")
    print()

    included, excluded = collect_files(verbose=True)

    print()
    print(f"Included: {len(included)} files")
    print(f"Excluded: {len(excluded)} files")

    # Safety gate: verify no secrets slipped through
    secret_leaks = [r for r, reason in excluded if reason == "SECRET"]
    included_secrets = [_rel(p) for p in included if _is_secret(_rel(p))]
    if included_secrets:
        print()
        print("ABORT: The following secret files would be included. This is a bug.")
        for s in included_secrets:
            print(f"  {s}")
        sys.exit(1)

    if dry_run:
        print()
        print("Included files:")
        for p in included:
            print(f"  {_rel(p)}")
        return

    print()
    print(f"Writing {output.name} ...")
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in included:
            zf.write(path, _rel(path))

    size_mb = output.stat().st_size / (1024 * 1024)
    print(f"Done. {output.name} ({size_mb:.1f} MB)")
    print()
    print("Safe to share. Secrets excluded:")
    for s in secret_leaks:
        print(f"  {s}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Create a secrets-free shareable zip of gopher-bot.")
    parser.add_argument("--output", "-o", type=Path, default=DEFAULT_OUTPUT,
                        help="Output zip path (default: timestamped in repo root)")
    parser.add_argument("--dry-run", action="store_true",
                        help="List included files without writing the zip")
    parser.add_argument("--verify", action="store_true",
                        help="Run exclusion checks only, then exit")
    args = parser.parse_args()

    if args.verify:
        ok = verify_exclusions()
        sys.exit(0 if ok else 1)

    build_zip(args.output, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
