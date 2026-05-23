"""
Migration 001 - Baseline schema stamp.

Stamps the database with schema version 1.
This migration has no structural changes; it only records that the
currently running database matches the v1 schema declared in
world_models/schema_version.py.
"""
from __future__ import annotations

VERSION = 1
DESCRIPTION = "Baseline schema stamp - record v1 schema in graph"


def up(driver) -> None:
    """Apply this migration. Idempotent."""
    from world_models.graph import set_schema_version

    set_schema_version(driver, VERSION)
