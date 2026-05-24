"""
Verify the Gopher-bot graph safety contract.

Runs each SC-NNN invariant from SAFETY_CONTRACT.md against Neo4j and reports
PASS/WARN/FAIL per invariant.

Usage:
    python scripts/verify_safety.py
    python scripts/verify_safety.py --json
    python scripts/verify_safety.py --fail-fast

Exit codes:
    0 - all safety checks pass
    1 - warnings only
    2 - one or more safety checks fail
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from coordinators.hands_policy import BLACKLIST_ACTIONS
from world_models.schema_version import CURRENT_SCHEMA_VERSION

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"

Result = dict[str, str]


def _result(status: str, name: str, detail: str = "") -> Result:
    return {"status": status, "name": name, "detail": detail}


def _single_record(driver, query: str, **params: Any):
    with driver.session() as session:
        return session.run(query, **params).single()


def _count(record, key: str) -> int:
    if record is None:
        return 0
    return int(record[key] or 0)


def check_sc_001(driver) -> Result:
    """SC-001 - Every Belief must have Claim or Source provenance."""
    record = _single_record(
        driver,
        """
        MATCH (b:Belief)
        WHERE NOT (b)<-[:SUPPORTS|EVIDENCES]-(:Claim)
          AND NOT (b)<-[:SUPPORTS|EVIDENCES]-(:Source)
        RETURN count(b) AS orphaned_beliefs
        """,
    )
    orphaned_beliefs = _count(record, "orphaned_beliefs")
    if orphaned_beliefs:
        return _result(
            FAIL,
            "SC-001 - Epistemic chain requires provenance",
            f"{orphaned_beliefs} Belief node(s) lack Claim/Source provenance",
        )
    return _result(PASS, "SC-001 - Epistemic chain requires provenance", "all Belief nodes have provenance")


def check_sc_002(driver) -> Result:
    """SC-002 - Every Doctrine must be authorized by an approved Proposal."""
    record = _single_record(
        driver,
        """
        MATCH (d:Doctrine)
        WHERE NOT (d)<-[:AUTHORIZES]-(:Proposal {status: 'APPROVED'})
        RETURN count(d) AS ungoverned_doctrines
        """,
    )
    ungoverned_doctrines = _count(record, "ungoverned_doctrines")
    if ungoverned_doctrines:
        return _result(
            FAIL,
            "SC-002 - Doctrine requires approved proposal",
            f"{ungoverned_doctrines} Doctrine node(s) lack approved Proposal authorization",
        )
    return _result(PASS, "SC-002 - Doctrine requires approved proposal", "all Doctrine nodes are approved")


def check_sc_003(driver) -> Result:
    """SC-003 - Every Principle must be reachable from a Belief."""
    record = _single_record(
        driver,
        """
        MATCH (p:Principle)
        WHERE NOT EXISTS {
            MATCH (:Belief)-[:GROUNDS|SUPPORTS*1..4]->(p)
        }
        RETURN count(p) AS unsupported_principles
        """,
    )
    unsupported_principles = _count(record, "unsupported_principles")
    if unsupported_principles:
        return _result(
            FAIL,
            "SC-003 - Principle elevation requires Belief support",
            f"{unsupported_principles} Principle node(s) are not reachable from Belief support",
        )
    return _result(PASS, "SC-003 - Principle elevation requires Belief support", "all Principle nodes have support")


def check_sc_004(driver) -> Result:
    """SC-004 - Epistemic chain edges must not form directed cycles."""
    try:
        record = _single_record(
            driver,
            """
            MATCH (start)
            WHERE start:Source
               OR start:Claim
               OR start:Belief
               OR start:Principle
               OR start:Doctrine
            CALL apoc.path.expandConfig(start, {
                relationshipFilter: 'YIELDS>|EVIDENCES>|SUPPORTS>|GROUNDS>|INSTANTIATES>',
                minLevel: 1,
                maxLevel: 10,
                uniqueness: 'RELATIONSHIP_PATH'
            }) YIELD path
            WHERE last(nodes(path)) = start
            RETURN count(path) AS cycles
            """,
        )
    except Exception as e:
        message = str(e)
        if "apoc" in message.lower() or "procedure" in message.lower():
            return _result(
                WARN,
                "SC-004 - Epistemic chain is acyclic",
                "skipped - APOC is required for cycle detection",
            )
        return _result(
            FAIL,
            "SC-004 - Epistemic chain is acyclic",
            f"cycle detection query failed: {e.__class__.__name__}",
        )

    cycles = _count(record, "cycles")
    if cycles:
        return _result(
            FAIL,
            "SC-004 - Epistemic chain is acyclic",
            f"{cycles} directed cycle(s) detected in epistemic chain edges",
        )
    return _result(PASS, "SC-004 - Epistemic chain is acyclic", "no directed cycles detected")


def check_sc_005(driver) -> Result:
    """SC-005 - AuditEntry nodes must include actor, action, and timestamp."""
    record = _single_record(
        driver,
        """
        MATCH (a:AuditEntry)
        WHERE a.coordinator_id IS NULL
           OR a.action IS NULL
           OR a.timestamp IS NULL
        RETURN count(a) AS incomplete_entries
        """,
    )
    incomplete_entries = _count(record, "incomplete_entries")
    if incomplete_entries:
        return _result(
            FAIL,
            "SC-005 - Audit log entries are complete",
            f"{incomplete_entries} AuditEntry node(s) are missing required fields",
        )
    return _result(PASS, "SC-005 - Audit log entries are complete", "all AuditEntry nodes are complete")


def check_sc_006(driver, *, expected_version: int = CURRENT_SCHEMA_VERSION) -> Result:
    """SC-006 - Graph SchemaVersion must match the codebase version."""
    record = _single_record(
        driver,
        """
        MATCH (s:SchemaVersion)
        RETURN s.version AS version
        LIMIT 1
        """,
    )
    if record is None or record["version"] is None:
        return _result(
            FAIL,
            "SC-006 - Schema version is current",
            f"missing SchemaVersion node; expected v{expected_version}",
        )

    try:
        actual_version = int(record["version"])
    except (TypeError, ValueError):
        return _result(
            FAIL,
            "SC-006 - Schema version is current",
            f"invalid SchemaVersion value; expected v{expected_version}",
        )

    if actual_version != expected_version:
        return _result(
            FAIL,
            "SC-006 - Schema version is current",
            f"graph schema version {actual_version} != expected {expected_version}",
        )
    return _result(PASS, "SC-006 - Schema version is current", f"v{actual_version}")


def check_sc_007(
    driver,
    *,
    blacklisted_actions: Iterable[str] = BLACKLIST_ACTIONS,
) -> Result:
    """SC-007 - Blacklisted actions must not appear in AuditEntry nodes."""
    blacklisted = sorted(str(action) for action in blacklisted_actions)
    record = _single_record(
        driver,
        """
        MATCH (a:AuditEntry)
        WHERE a.action IN $blacklisted
        RETURN count(a) AS blacklist_violations
        """,
        blacklisted=blacklisted,
    )
    blacklist_violations = _count(record, "blacklist_violations")
    if blacklist_violations:
        return _result(
            FAIL,
            "SC-007 - Blacklisted actions are unexecuted",
            f"{blacklist_violations} AuditEntry node(s) record blacklisted actions",
        )
    return _result(PASS, "SC-007 - Blacklisted actions are unexecuted", "no blacklisted actions recorded")


def run_checks(
    driver,
    *,
    fail_fast: bool = False,
    expected_version: int = CURRENT_SCHEMA_VERSION,
    blacklisted_actions: Iterable[str] = BLACKLIST_ACTIONS,
) -> list[Result]:
    checks: list[tuple[str, Callable[[Any], Result]]] = [
        ("SC-001 - Epistemic chain requires provenance", check_sc_001),
        ("SC-002 - Doctrine requires approved proposal", check_sc_002),
        ("SC-003 - Principle elevation requires Belief support", check_sc_003),
        ("SC-004 - Epistemic chain is acyclic", check_sc_004),
        ("SC-005 - Audit log entries are complete", check_sc_005),
        (
            "SC-006 - Schema version is current",
            lambda passed_driver: check_sc_006(passed_driver, expected_version=expected_version),
        ),
        (
            "SC-007 - Blacklisted actions are unexecuted",
            lambda passed_driver: check_sc_007(passed_driver, blacklisted_actions=blacklisted_actions),
        ),
    ]

    results: list[Result] = []
    for name, check_fn in checks:
        try:
            result = check_fn(driver)
        except Exception as e:
            result = _result(FAIL, name, f"check query failed: {e.__class__.__name__}")
        results.append(result)
        if fail_fast and result["status"] == FAIL:
            break
    return results


def run_safety_checks(
    *,
    driver_factory: Callable[[], Any] | None = None,
    fail_fast: bool = False,
    expected_version: int = CURRENT_SCHEMA_VERSION,
    blacklisted_actions: Iterable[str] = BLACKLIST_ACTIONS,
) -> list[Result]:
    if driver_factory is None:
        from world_models.graph import connect as driver_factory

    driver = None
    try:
        driver = driver_factory()
        return run_checks(
            driver,
            fail_fast=fail_fast,
            expected_version=expected_version,
            blacklisted_actions=blacklisted_actions,
        )
    except Exception as e:
        return [
            _result(
                FAIL,
                "Neo4j connection",
                f"could not run safety checks: {e.__class__.__name__}",
            )
        ]
    finally:
        close_driver = getattr(driver, "close", None)
        if callable(close_driver):
            close_driver()


def _summary(results: list[Result]) -> dict[str, int]:
    return {
        "pass": sum(1 for result in results if result["status"] == PASS),
        "warn": sum(1 for result in results if result["status"] == WARN),
        "fail": sum(1 for result in results if result["status"] == FAIL),
    }


def exit_code_for(results: list[Result]) -> int:
    summary = _summary(results)
    if summary["fail"]:
        return 2
    if summary["warn"]:
        return 1
    return 0


def _print_human(results: list[Result]) -> None:
    print("=" * 60)
    print("  Gopher-bot Safety Contract Verification")
    print("=" * 60)
    for result in results:
        icon = {"PASS": "  OK  ", "WARN": " WARN ", "FAIL": " FAIL "}[result["status"]]
        line = f"[{icon}] {result['name']}"
        if result["detail"]:
            line += f" - {result['detail']}"
        print(line)

    summary = _summary(results)
    print()
    print("=" * 60)
    print(f"  {summary['pass']} passed  |  {summary['warn']} warnings  |  {summary['fail']} failed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify Gopher-bot graph safety contract")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of human-readable text")
    parser.add_argument("--fail-fast", action="store_true", help="Stop at first failed invariant")
    args = parser.parse_args(argv)

    results = run_safety_checks(fail_fast=args.fail_fast)
    if args.json:
        print(json.dumps({"results": results, "summary": _summary(results)}, indent=2))
    else:
        _print_human(results)
    return exit_code_for(results)


if __name__ == "__main__":
    sys.exit(main())
