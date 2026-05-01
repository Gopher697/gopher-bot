"""Configuration loading and validation.

The server intentionally does not discover projects from the filesystem. Every
project root and every runnable command must be explicitly listed in config.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    """Raised when a configuration file is missing or malformed."""


@dataclass(frozen=True)
class Project:
    """A project allowlist entry from config/projects.yaml."""

    name: str
    root: Path
    summary_file: str = "PROJECT.md"
    notes_dir: str = "notes"
    session_notes_dir: str = "notes/sessions"


@dataclass(frozen=True)
class AllowedCommand:
    """A command allowlist entry from config/allowed_commands.yaml."""

    name: str
    argv: tuple[str, ...]
    projects: tuple[str, ...]
    description: str = ""


@dataclass(frozen=True)
class WorkbenchConfig:
    """Fully loaded server configuration."""

    projects: dict[str, Project]
    commands: dict[str, AllowedCommand]


def load_yaml(path: Path) -> Any:
    """Load a YAML file and require a mapping at the top level."""

    if not path.exists():
        raise ConfigError(f"Missing config file: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"Config file must contain a mapping: {path}")
    return data


def load_projects(path: Path) -> dict[str, Project]:
    """Load project roots from config/projects.yaml."""

    data = load_yaml(path)
    raw_projects = data.get("projects")
    if not isinstance(raw_projects, list):
        raise ConfigError("projects.yaml must contain a 'projects' list")

    projects: dict[str, Project] = {}
    for item in raw_projects:
        if not isinstance(item, dict):
            raise ConfigError("Each project entry must be a mapping")
        name = item.get("name")
        root = item.get("root")
        if not isinstance(name, str) or not name.strip():
            raise ConfigError("Project entry is missing a non-empty name")
        if not isinstance(root, str) or not root.strip():
            raise ConfigError(f"Project {name!r} is missing a root")
        if name in projects:
            raise ConfigError(f"Duplicate project name: {name}")

        root_path = Path(root).expanduser().resolve()
        projects[name] = Project(
            name=name,
            root=root_path,
            summary_file=str(item.get("summary_file", "PROJECT.md")),
            notes_dir=str(item.get("notes_dir", "notes")),
            session_notes_dir=str(item.get("session_notes_dir", "notes/sessions")),
        )

    return projects


def load_allowed_commands(path: Path) -> dict[str, AllowedCommand]:
    """Load command argv definitions from config/allowed_commands.yaml."""

    data = load_yaml(path)
    raw_commands = data.get("commands")
    if not isinstance(raw_commands, list):
        raise ConfigError("allowed_commands.yaml must contain a 'commands' list")

    commands: dict[str, AllowedCommand] = {}
    for item in raw_commands:
        if not isinstance(item, dict):
            raise ConfigError("Each command entry must be a mapping")
        name = item.get("name")
        argv = item.get("argv")
        projects = item.get("projects")
        description = item.get("description", "")
        if not isinstance(name, str) or not name.strip():
            raise ConfigError("Command entry is missing a non-empty name")
        if not isinstance(argv, list) or not argv or not all(isinstance(part, str) for part in argv):
            raise ConfigError(f"Command {name!r} must define a non-empty argv string list")
        if (
            not isinstance(projects, list)
            or not projects
            or not all(isinstance(project, str) and project.strip() for project in projects)
        ):
            raise ConfigError(f"Command {name!r} must define a non-empty projects string list")
        if not isinstance(description, str):
            raise ConfigError(f"Command {name!r} description must be a string")
        if name in commands:
            raise ConfigError(f"Duplicate command name: {name}")

        commands[name] = AllowedCommand(
            name=name,
            argv=tuple(argv),
            projects=tuple(projects),
            description=description,
        )

    return commands


def load_config(config_dir: Path) -> WorkbenchConfig:
    """Load all server configuration from a directory."""

    config_dir = config_dir.resolve()
    return WorkbenchConfig(
        projects=load_projects(config_dir / "projects.yaml"),
        commands=load_allowed_commands(config_dir / "allowed_commands.yaml"),
    )
