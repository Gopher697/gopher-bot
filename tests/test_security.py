from pathlib import Path
import subprocess

import pytest

import gopher_workbench_mcp.workbench as workbench_module
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
    projects: ["demo"]
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


def test_search_project_text_finds_expected_text() -> None:
    workspace = make_workspace("text-search-normal")
    config_dir = workspace / "config"
    project_root = workspace / "project"
    project_root.mkdir()
    write_config(config_dir, project_root)
    (project_root / "app.py").write_text("alpha\nneedle here\n", encoding="utf-8")

    workbench = Workbench(config_dir=config_dir, logs_dir=workspace / "logs")

    assert workbench.search_project_text("demo", "needle") == [
        {"file": "app.py", "line": 2, "text": "needle here"}
    ]


def test_search_project_text_is_confined_to_project_root() -> None:
    workspace = make_workspace("text-search-confined")
    config_dir = workspace / "config"
    project_root = workspace / "project"
    project_root.mkdir()
    write_config(config_dir, project_root)
    outside = workspace / "outside.txt"
    outside.write_text("secret needle\n", encoding="utf-8")
    symlink = project_root / "linked.txt"
    try:
        symlink.symlink_to(outside)
    except OSError:
        pytest.skip("Symlink creation is not available in this environment")

    workbench = Workbench(config_dir=config_dir, logs_dir=workspace / "logs")

    assert workbench.search_project_text("demo", "secret") == []


def test_search_project_text_excludes_sensitive_and_generated_paths() -> None:
    workspace = make_workspace("text-search-excludes")
    config_dir = workspace / "config"
    project_root = workspace / "project"
    project_root.mkdir()
    write_config(config_dir, project_root)
    excluded_paths = [
        project_root / ".git" / "config",
        project_root / ".env",
        project_root / ".env.local",
        project_root / "logs" / "app.log",
        project_root / ".pytest_cache" / "cache.txt",
        project_root / "node_modules" / "pkg" / "index.js",
        project_root / "dist" / "bundle.js",
        project_root / "build" / "output.txt",
        project_root / "notes" / "sessions" / "20260503T000000Z.md",
        project_root / ".venv" / "pyvenv.cfg",
        project_root / "__pycache__" / "module.pyc",
    ]
    for path in excluded_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("excluded needle\n", encoding="utf-8")
    (project_root / "src").mkdir()
    (project_root / "src" / "app.txt").write_text("included needle\n", encoding="utf-8")

    workbench = Workbench(config_dir=config_dir, logs_dir=workspace / "logs")

    assert workbench.search_project_text("demo", "needle") == [
        {"file": "src\\app.txt", "line": 1, "text": "included needle"}
    ]


def test_search_project_text_treats_dash_query_as_text() -> None:
    workspace = make_workspace("text-search-dash-query")
    config_dir = workspace / "config"
    project_root = workspace / "project"
    project_root.mkdir()
    write_config(config_dir, project_root)
    (project_root / "README.md").write_text("--pre is documented text\n", encoding="utf-8")

    workbench = Workbench(config_dir=config_dir, logs_dir=workspace / "logs")

    assert workbench.search_project_text("demo", "--pre") == [
        {"file": "README.md", "line": 1, "text": "--pre is documented text"}
    ]


def test_search_project_text_rg_uses_fixed_args_with_dash_query(monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = make_workspace("text-search-rg-argv")
    config_dir = workspace / "config"
    project_root = workspace / "project"
    project_root.mkdir()
    write_config(config_dir, project_root)
    captured: dict[str, object] = {}

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        captured.update(kwargs)
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="")

    monkeypatch.setattr(workbench_module, "which", lambda name: "rg.exe")
    monkeypatch.setattr(subprocess, "run", fake_run)

    workbench = Workbench(config_dir=config_dir, logs_dir=workspace / "logs")

    assert workbench.search_project_text("demo", "--pre") == []
    argv = captured["argv"]
    assert argv[-3:] == ["--", "--pre", "."]
    assert captured["cwd"] == project_root.resolve()
    assert captured["shell"] is False


def test_search_project_text_glob_filters_and_rejects_escape() -> None:
    workspace = make_workspace("text-search-glob")
    config_dir = workspace / "config"
    project_root = workspace / "project"
    project_root.mkdir()
    write_config(config_dir, project_root)
    (project_root / "app.py").write_text("needle\n", encoding="utf-8")
    (project_root / "app.md").write_text("needle\n", encoding="utf-8")
    (project_root / "src" / "nested").mkdir(parents=True)
    (project_root / "src" / "nested" / "app.py").write_text("needle\n", encoding="utf-8")
    (project_root / "src" / "nested" / "app.md").write_text("needle\n", encoding="utf-8")

    workbench = Workbench(config_dir=config_dir, logs_dir=workspace / "logs")

    assert workbench.search_project_text("demo", "needle", "*.py") == [
        {"file": "app.py", "line": 1, "text": "needle"}
    ]
    assert workbench.search_project_text("demo", "needle", "src/**/*.py") == [
        {"file": "src\\nested\\app.py", "line": 1, "text": "needle"}
    ]
    with pytest.raises(WorkbenchError, match="path traversal"):
        workbench.search_project_text("demo", "needle", "../*.py")
    with pytest.raises(WorkbenchError, match="project-relative"):
        workbench.search_project_text("demo", "needle", "D:/outside/*.py")


def test_git_status_uses_noninteractive_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = make_workspace("git-subprocess")
    config_dir = workspace / "config"
    project_root = workspace / "project"
    project_root.mkdir()
    write_config(config_dir, project_root)
    workbench = Workbench(config_dir=config_dir, logs_dir=workspace / "logs")
    captured: dict[str, object] = {}

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        captured.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert workbench.git_status("demo") == "ok"
    assert captured["argv"] == ["git", "status", "--short"]
    assert captured["cwd"] == project_root.resolve()
    assert captured["stdin"] is subprocess.DEVNULL
    assert captured["stdout"] is subprocess.PIPE
    assert captured["stderr"] is subprocess.PIPE
    assert captured["shell"] is False
    assert captured["timeout"] == 30
    assert captured["env"]["GIT_TERMINAL_PROMPT"] == "0"  # type: ignore[index]
    assert captured["env"]["GIT_PAGER"] == "cat"  # type: ignore[index]
    assert captured["env"]["GIT_CONFIG_KEY_0"] == "safe.directory"  # type: ignore[index]
    assert captured["env"]["GIT_CONFIG_VALUE_0"] == str(project_root.resolve())  # type: ignore[index]


def test_allowed_command_uses_noninteractive_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = make_workspace("allowed-subprocess")
    config_dir = workspace / "config"
    project_root = workspace / "project"
    project_root.mkdir()
    write_config(config_dir, project_root)
    workbench = Workbench(config_dir=config_dir, logs_dir=workspace / "logs")
    captured: dict[str, object] = {}

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        captured.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, stdout="Python 3", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = workbench.run_allowed_command("demo", "ok")

    assert result["stdout"] == "Python 3"
    assert captured["argv"] == ["python", "--version"]
    assert captured["cwd"] == project_root.resolve()
    assert captured["stdin"] is subprocess.DEVNULL
    assert captured["stdout"] is subprocess.PIPE
    assert captured["stderr"] is subprocess.PIPE
    assert captured["shell"] is False
    assert captured["timeout"] == 120


def test_pytest_command_works_for_gopher_workbench_mcp(monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = make_workspace("project-scoped-pytest")
    config_dir = workspace / "config"
    project_root = workspace / "project"
    project_root.mkdir()
    config_dir.mkdir()
    (config_dir / "projects.yaml").write_text(
        f"""
projects:
  - name: gopher-workbench-mcp
    root: "{project_root.as_posix()}"
""",
        encoding="utf-8",
    )
    (config_dir / "allowed_commands.yaml").write_text(
        """
commands:
  - name: pytest
    projects: ["gopher-workbench-mcp"]
    argv: ["python", "-m", "pytest"]
""",
        encoding="utf-8",
    )
    workbench = Workbench(config_dir=config_dir, logs_dir=workspace / "logs")
    captured: dict[str, object] = {}

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        captured.update(kwargs)
        return subprocess.CompletedProcess(argv, 0, stdout="passed", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = workbench.run_allowed_command("gopher-workbench-mcp", "pytest")

    assert result["returncode"] == 0
    assert result["stdout"] == "passed"
    assert captured["argv"] == ["python", "-m", "pytest"]
    assert captured["cwd"] == project_root.resolve()


def test_allowed_command_rejects_project_outside_command_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = make_workspace("project-scoped-rejection")
    config_dir = workspace / "config"
    allowed_root = workspace / "allowed"
    other_root = workspace / "other"
    allowed_root.mkdir()
    other_root.mkdir()
    config_dir.mkdir()
    (config_dir / "projects.yaml").write_text(
        f"""
projects:
  - name: gopher-workbench-mcp
    root: "{allowed_root.as_posix()}"
  - name: other-project
    root: "{other_root.as_posix()}"
""",
        encoding="utf-8",
    )
    (config_dir / "allowed_commands.yaml").write_text(
        """
commands:
  - name: pytest
    projects: ["gopher-workbench-mcp"]
    argv: ["python", "-m", "pytest"]
""",
        encoding="utf-8",
    )
    workbench = Workbench(config_dir=config_dir, logs_dir=workspace / "logs")

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError("subprocess.run should not be called")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(WorkbenchError, match="not allowlisted for project"):
        workbench.run_allowed_command("other-project", "pytest")
