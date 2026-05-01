from pathlib import Path

import pytest

from gopher_workbench_mcp.workbench import Workbench, WorkbenchError, safe_relative_path
from helpers import make_workspace


def write_config(config_dir: Path, project_root: Path) -> None:
    config_dir.mkdir()
    (config_dir / "projects.yaml").write_text(
        f"""
projects:
  - name: demo
    root: "{project_root.as_posix()}"
    summary_file: "PROJECT.md"
    notes_dir: "notes"
    session_notes_dir: "notes/sessions"
""",
        encoding="utf-8",
    )
    (config_dir / "allowed_commands.yaml").write_text(
        """
commands:
  - name: ok
    argv: ["python", "--version"]
""",
        encoding="utf-8",
    )


def test_safe_relative_path_rejects_path_traversal() -> None:
    workspace = make_workspace("safe-path")
    root = (workspace / "project").resolve()
    root.mkdir()

    with pytest.raises(WorkbenchError, match="escapes project root"):
        safe_relative_path(root, "../outside.txt")


def test_summary_file_path_traversal_is_rejected() -> None:
    workspace = make_workspace("summary-traversal")
    config_dir = workspace / "config"
    project_root = workspace / "project"
    project_root.mkdir()
    write_config(config_dir, project_root)
    (config_dir / "projects.yaml").write_text(
        f"""
projects:
  - name: demo
    root: "{project_root.as_posix()}"
    summary_file: "../outside.md"
""",
        encoding="utf-8",
    )

    workbench = Workbench(config_dir=config_dir, logs_dir=workspace / "logs")

    with pytest.raises(WorkbenchError, match="escapes project root"):
        workbench.read_project_summary("demo")


def test_run_allowed_command_rejects_unknown_command() -> None:
    workspace = make_workspace("command-allowlist")
    config_dir = workspace / "config"
    project_root = workspace / "project"
    project_root.mkdir()
    write_config(config_dir, project_root)
    workbench = Workbench(config_dir=config_dir, logs_dir=workspace / "logs")

    with pytest.raises(WorkbenchError, match="not allowlisted"):
        workbench.run_allowed_command("demo", "rm-rf")


def test_search_notes_rejects_symlink_escape() -> None:
    workspace = make_workspace("notes-symlink")
    config_dir = workspace / "config"
    project_root = workspace / "project"
    project_root.mkdir()
    notes_dir = project_root / "notes"
    notes_dir.mkdir()
    outside = workspace / "outside.md"
    outside.write_text("secret needle\n", encoding="utf-8")
    write_config(config_dir, project_root)

    symlink = notes_dir / "escape.md"
    try:
        symlink.symlink_to(outside)
    except OSError:
        pytest.skip("Symlink creation is not available in this environment")

    workbench = Workbench(config_dir=config_dir, logs_dir=workspace / "logs")

    with pytest.raises(WorkbenchError, match="escapes project root"):
        workbench.search_project_notes("demo", "needle")


def test_search_notes_logs_query_length_not_query_text() -> None:
    workspace = make_workspace("query-log-redaction")
    config_dir = workspace / "config"
    project_root = workspace / "project"
    project_root.mkdir()
    notes_dir = project_root / "notes"
    notes_dir.mkdir()
    (notes_dir / "note.md").write_text("find me\n", encoding="utf-8")
    write_config(config_dir, project_root)

    workbench = Workbench(config_dir=config_dir, logs_dir=workspace / "logs")
    workbench.search_project_notes("demo", "find")
    log_text = (workspace / "logs" / "tool-calls.jsonl").read_text(encoding="utf-8")

    assert '"query_length": 4' in log_text
    assert '"query":' not in log_text
