from __future__ import annotations

import importlib.util
import io
import sys
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
STARTUP_SCRIPT = REPO_ROOT / "scripts" / "startup.py"


def load_startup_module():
    spec = importlib.util.spec_from_file_location("startup_script", STARTUP_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_commitments(path: Path) -> None:
    path.write_text(
        """# Agent Commitments

### C-001 - Build governance foundation

| Field | Value |
|---|---|
| `id` | C-001 |
| `status` | active |
| `description` | Build governance foundation |

### C-002 - Build knowledge graph substrate

| Field | Value |
|---|---|
| `id` | C-002 |
| `status` | blocked |
| `description` | Build knowledge graph substrate |

---

## Schema Reference

| Field | Description |
|---|---|
| `id` | Unique identifier (C-NNN) |
| `status` | `active` / `paused` / `superseded` / `blocked` / `closed` |
| `description` | What is committed to |
""",
        encoding="utf-8",
    )


def test_startup_reports_real_files_and_appends_action_log(tmp_path):
    startup = load_startup_module()
    startup.query_world_model_summary = lambda: "0 entities in global ✓"
    now = datetime(2026, 5, 18, 21, 30, 0)

    (tmp_path / "AGENT_CHARTER.md").write_text(
        "# Persistent Agent Charter\n\n**Status:** Ratified v0.6\n**Version:** 0.6\n",
        encoding="utf-8",
    )
    write_commitments(tmp_path / "AGENT_COMMITMENTS.md")
    (tmp_path / "proposals" / "pending").mkdir(parents=True)
    (tmp_path / "proposals" / "pending" / ".gitkeep").write_text("", encoding="utf-8")

    output = io.StringIO()
    exit_code = startup.run_startup(root=tmp_path, now=now, out=output)

    report = output.getvalue()
    assert exit_code == 0
    assert "[1] Charter .............. Ratified v0.6" in report
    assert "[2] Commitments .......... 1 active, 1 blocked" in report
    assert "      C-001  Build governance foundation" in report
    assert "      C-002  Build knowledge graph substrate (blocked)" in report
    assert "[3] World models ......... 0 entities in global ✓" in report
    assert "[4] Pending proposals .... 0" in report
    assert "[5] Autonomy level ....... Tier 2 default (no global file found)" in report
    assert "Status: READY" in report

    action_log = tmp_path / "logs" / "actions" / "20260518.md"
    action_log_text = action_log.read_text(encoding="utf-8")
    assert "# Action Log — 2026-05-18" in action_log_text
    assert "### [2026-05-18T21:30:00] — Coordinator startup" in action_log_text
    assert "| result | COMPLETE |" in action_log_text


def test_startup_marks_incomplete_when_charter_is_not_ratified(tmp_path):
    startup = load_startup_module()
    startup.query_world_model_summary = lambda: "0 entities in global ✓"
    now = datetime(2026, 5, 18, 21, 30, 0)

    (tmp_path / "AGENT_CHARTER.md").write_text(
        "# Persistent Agent Charter\n\n**Status:** Draft v0.6\n**Version:** 0.6\n",
        encoding="utf-8",
    )
    write_commitments(tmp_path / "AGENT_COMMITMENTS.md")
    (tmp_path / "proposals" / "pending").mkdir(parents=True)

    output = io.StringIO()
    exit_code = startup.run_startup(root=tmp_path, now=now, out=output)

    report = output.getvalue()
    assert exit_code == 1
    assert "WARNING: AGENT_CHARTER.md Status does not contain Ratified" in report
    assert "Status: INCOMPLETE" in report
    assert "charter not ratified" in report

    action_log = tmp_path / "logs" / "actions" / "20260518.md"
    assert "| result | INCOMPLETE — charter not ratified |" in action_log.read_text(
        encoding="utf-8"
    )
