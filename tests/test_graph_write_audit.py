from __future__ import annotations

import json
from datetime import datetime, timezone

from tests.helpers import make_workspace


def test_audit_graph_write_appends_jsonl_entry():
    from utils.graph_write_audit import audit_graph_write

    writes = []
    log_dir = make_workspace("graph-audit-entry")

    audit_graph_write(
        action="create_belief",
        node_label="Belief",
        coordinator="archivist",
        properties={"belief_id": "b1"},
        log_dir_fn=lambda: log_dir,
        write_fn=lambda path, line: writes.append((path, line)),
    )

    assert len(writes) == 1
    path, line = writes[0]
    entry = json.loads(line)
    assert path.parent == log_dir
    assert path.name.endswith(".jsonl")
    assert entry["action"] == "create_belief"
    assert entry["node_label"] == "Belief"
    assert entry["coordinator"] == "archivist"
    assert entry["properties"] == {"belief_id": "b1"}


def test_audit_entry_contains_utc_timestamp():
    from utils.graph_write_audit import audit_graph_write

    writes = []
    log_dir = make_workspace("graph-audit-timestamp")

    audit_graph_write(
        action="create_claim",
        node_label="Claim",
        log_dir_fn=lambda: log_dir,
        write_fn=lambda _path, line: writes.append(line),
    )

    entry = json.loads(writes[0])
    parsed = datetime.fromisoformat(entry["ts"].replace("Z", "+00:00"))
    assert parsed.tzinfo == timezone.utc
    assert entry["ts"].endswith("Z")


def test_audit_entry_omits_sensitive_property_keys():
    from utils.graph_write_audit import audit_graph_write

    writes = []
    log_dir = make_workspace("graph-audit-redaction")

    audit_graph_write(
        action="add_entity",
        node_label="Entity",
        properties={"name": "test", "api_key": "secret"},
        log_dir_fn=lambda: log_dir,
        write_fn=lambda _path, line: writes.append(line),
    )

    entry = json.loads(writes[0])
    assert entry["properties"] == {"name": "test"}
    assert "api_key" not in entry["properties"]


def test_audit_graph_write_never_raises_on_write_failure():
    from utils.graph_write_audit import audit_graph_write

    log_dir = make_workspace("graph-audit-write-failure")

    def fail_write(_path, _line):
        raise OSError("disk full")

    audit_graph_write(
        action="create_doctrine",
        node_label="Doctrine",
        log_dir_fn=lambda: log_dir,
        write_fn=fail_write,
    )


def test_audit_graph_write_creates_log_dir():
    from utils.graph_write_audit import audit_graph_write

    log_dir = make_workspace("graph-audit-create-dir") / "logs" / "graph_writes"
    writes = []

    audit_graph_write(
        action="create_skill",
        node_label="Skill",
        log_dir_fn=lambda: log_dir,
        write_fn=lambda path, line: writes.append((path, line)),
    )

    assert log_dir.exists()
    assert writes[0][0].parent == log_dir


def test_check_write_policy_is_noop_in_phase1():
    from utils.graph_write_audit import check_write_policy

    check_write_policy("Doctrine", "create_doctrine")


def test_proposal_required_error_is_importable():
    from utils.graph_write_audit import ProposalRequiredError

    assert issubclass(ProposalRequiredError, Exception)
