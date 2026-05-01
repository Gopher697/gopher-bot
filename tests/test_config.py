import pytest

from gopher_workbench_mcp.config import ConfigError, load_allowed_commands, load_config
from helpers import make_workspace


def test_load_config_reads_projects_and_commands() -> None:
    workspace = make_workspace("config-loading")
    config_dir = workspace / "config"
    project_root = workspace / "project"
    config_dir.mkdir()
    project_root.mkdir()
    (config_dir / "projects.yaml").write_text(
        f"""
projects:
  - name: demo
    root: "{project_root.as_posix()}"
    summary_file: "README.md"
""",
        encoding="utf-8",
    )
    (config_dir / "allowed_commands.yaml").write_text(
        """
commands:
  - name: test
    argv: ["python", "-m", "pytest"]
""",
        encoding="utf-8",
    )

    config = load_config(config_dir)

    assert config.projects["demo"].root == project_root.resolve()
    assert config.projects["demo"].summary_file == "README.md"
    assert config.commands["test"].argv == ("python", "-m", "pytest")


def test_load_allowed_commands_requires_argv_list() -> None:
    workspace = make_workspace("bad-command-config")
    path = workspace / "allowed_commands.yaml"
    path.write_text(
        """
commands:
  - name: unsafe
    argv: "echo nope"
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="non-empty argv"):
        load_allowed_commands(path)
