"""MCP transport layer for gopher-workbench-mcp."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .workbench import Workbench, validate_startup_config


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_DIR = ROOT / "config"
DEFAULT_LOGS_DIR = ROOT / "logs"


SOPS = {
    "sop://ai-coding-loop": ROOT / "sops" / "ai-coding-loop.md",
    "sop://modding-workflow": ROOT / "sops" / "modding-workflow.md",
    "sop://troubleshooting": ROOT / "sops" / "troubleshooting.md",
    "sop://assistant-style": ROOT / "sops" / "assistant-style.md",
}


def create_server(config_dir: Path = DEFAULT_CONFIG_DIR, logs_dir: Path = DEFAULT_LOGS_DIR) -> FastMCP:
    """Create a configured FastMCP server instance."""

    validate_startup_config(config_dir)
    workbench = Workbench(config_dir=config_dir, logs_dir=logs_dir)
    mcp = FastMCP("gopher-workbench-mcp")

    @mcp.resource("sop://ai-coding-loop")
    def ai_coding_loop() -> str:
        return SOPS["sop://ai-coding-loop"].read_text(encoding="utf-8")

    @mcp.resource("sop://modding-workflow")
    def modding_workflow() -> str:
        return SOPS["sop://modding-workflow"].read_text(encoding="utf-8")

    @mcp.resource("sop://troubleshooting")
    def troubleshooting() -> str:
        return SOPS["sop://troubleshooting"].read_text(encoding="utf-8")

    @mcp.resource("sop://assistant-style")
    def assistant_style() -> str:
        return SOPS["sop://assistant-style"].read_text(encoding="utf-8")

    @mcp.tool()
    def list_projects() -> list[dict[str, str]]:
        """List explicitly configured projects."""

        return workbench.list_projects()

    @mcp.tool()
    def read_project_summary(project: str) -> str:
        """Read the configured summary file for an allowlisted project."""

        return workbench.read_project_summary(project)

    @mcp.tool()
    def search_project_notes(project: str, query: str) -> list[dict[str, Any]]:
        """Search project notes under the configured notes directory."""

        return workbench.search_project_notes(project, query)

    @mcp.tool()
    def git_status(project: str) -> str:
        """Return git status --short for an allowlisted project."""

        return workbench.git_status(project)

    @mcp.tool()
    def git_diff(project: str) -> str:
        """Return git diff for an allowlisted project."""

        return workbench.git_diff(project)

    @mcp.tool()
    def run_allowed_command(project: str, command_name: str) -> dict[str, Any]:
        """Run a command by allowlist name inside the configured project root."""

        return workbench.run_allowed_command(project, command_name)

    @mcp.tool()
    def save_session_note(project: str, note: str) -> dict[str, str]:
        """Append a timestamped session note inside the project's session notes folder."""

        return workbench.save_session_note(project, note)

    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the gopher workbench MCP server.")
    parser.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG_DIR)
    parser.add_argument("--logs-dir", type=Path, default=DEFAULT_LOGS_DIR)
    args = parser.parse_args()
    create_server(config_dir=args.config_dir, logs_dir=args.logs_dir).run()


if __name__ == "__main__":
    main()

