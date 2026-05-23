"""
Run pending graph schema migrations.

Usage:
    python scripts/run_migrations.py [--dry-run]

Options:
    --dry-run   Print what would be applied without making changes.

Exit codes:
    0 - all migrations applied (or nothing to do)
    1 - error during migration
"""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path
from types import ModuleType
from typing import Iterable, TextIO

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from world_models.graph import close, connect, get_schema_version, set_schema_version

MIGRATIONS_DIR = REPO_ROOT / "scripts" / "migrations"


def discover_migrations(migrations_dir: Path = MIGRATIONS_DIR) -> list[ModuleType]:
    modules = []
    for path in sorted(migrations_dir.glob("migrate_[0-9][0-9][0-9]_*.py")):
        module_name = f"scripts.migrations.{path.stem}"
        modules.append(importlib.import_module(module_name))
    return sorted(modules, key=lambda module: module.VERSION)


def _migration_label(migration) -> str:
    description = getattr(migration, "DESCRIPTION", "")
    suffix = f" - {description}" if description else ""
    return f"{migration.VERSION:03d}{suffix}"


def run_migrations(
    driver,
    *,
    migrations: Iterable | None = None,
    current_version: int | None = None,
    dry_run: bool = False,
    out: TextIO = sys.stdout,
) -> int:
    graph_version = get_schema_version(driver) if current_version is None else current_version
    graph_version = 0 if graph_version is None else int(graph_version)
    migration_list = list(discover_migrations() if migrations is None else migrations)

    if not migration_list:
        print("OK no migrations found", file=out)
        return 0

    for migration in sorted(migration_list, key=lambda module: module.VERSION):
        label = _migration_label(migration)
        if migration.VERSION <= graph_version:
            print(f"SKIP {label} (graph already at v{graph_version})", file=out)
            continue

        if dry_run:
            print(f"DRY-RUN {label}", file=out)
            continue

        try:
            migration.up(driver)
            set_schema_version(driver, migration.VERSION)
            graph_version = migration.VERSION
            print(f"APPLIED {label}", file=out)
        except Exception as exc:
            print(f"FAIL {label}: {exc}", file=out)
            return 1

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run pending graph schema migrations")
    parser.add_argument("--dry-run", action="store_true", help="Print pending migrations without applying")
    args = parser.parse_args(argv)

    try:
        driver = connect()
    except Exception as exc:
        print(f"FAIL could not connect to Neo4j: {exc}")
        return 1

    try:
        return run_migrations(driver, dry_run=args.dry_run)
    finally:
        close(driver)


if __name__ == "__main__":
    sys.exit(main())
