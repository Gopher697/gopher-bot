"""Core workbench operations used by the MCP transport layer."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from fnmatch import fnmatchcase
from pathlib import Path
from shutil import which

from .config import AllowedCommand, ConfigError, Project, WorkbenchConfig, load_config


class WorkbenchError(ValueError):
    """Raised when a tool request is rejected or cannot be completed safely."""


MAX_TEXT_SEARCH_RESULTS = 200
EXCLUDED_SEARCH_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "cache",
    "caches",
    "dist",
    "logs",
    "node_modules",
    "pytest_tmp",
    "target",
    "venv",
}
EXCLUDED_SEARCH_FILE_NAMES = {".env"}
EXCLUDED_SEARCH_FILE_PREFIXES = (".env.",)
RG_EXCLUDE_GLOBS = [
    "!.git/**",
    "!.env",
    "!.env.*",
    "!logs/**",
    "!cache/**",
    "!caches/**",
    "!node_modules/**",
    "!dist/**",
    "!build/**",
    "!target/**",
    "!.venv/**",
    "!venv/**",
    "!__pycache__/**",
    "!.pytest_cache/**",
    "!.mypy_cache/**",
    "!.ruff_cache/**",
    "!.tox/**",
]


def safe_relative_path(root: Path, relative: str) -> Path:
    """Resolve a project-relative path and reject escapes outside the root."""

    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise WorkbenchError(f"Path escapes project root: {relative}") from exc
    return candidate


def validate_search_glob(glob: str | None) -> str | None:
    """Validate an optional project-relative include glob."""

    if glob is None:
        return None
    cleaned = glob.strip().replace("\\", "/")
    if not cleaned:
        return None
    if cleaned.startswith("/") or cleaned.startswith("-") or ":" in cleaned:
        raise WorkbenchError("Search glob must be a project-relative include pattern")
    if any(part == ".." for part in cleaned.split("/")):
        raise WorkbenchError("Search glob must not contain path traversal")
    return cleaned


def is_excluded_search_path(path: Path, root: Path, session_notes_dir: str) -> bool:
    """Return whether a project-relative path is excluded from text search."""

    relative = path.relative_to(root)
    parts = set(relative.parts)
    if parts & EXCLUDED_SEARCH_DIRS:
        return True
    if path.name in EXCLUDED_SEARCH_FILE_NAMES:
        return True
    if path.name.startswith(EXCLUDED_SEARCH_FILE_PREFIXES):
        return True
    session_notes = safe_relative_path(root, session_notes_dir)
    try:
        path.resolve().relative_to(session_notes.resolve())
    except ValueError:
        return False
    return True


def matches_search_glob(relative: Path, glob: str) -> bool:
    """Match project-relative globs with POSIX separators for stable MCP behavior."""

    path_parts = relative.as_posix().split("/")
    glob_parts = glob.split("/")

    def match_from(glob_index: int, path_index: int) -> bool:
        if glob_index == len(glob_parts):
            return path_index == len(path_parts)
        glob_part = glob_parts[glob_index]
        if glob_part == "**":
            return any(
                match_from(glob_index + 1, next_path_index)
                for next_path_index in range(path_index, len(path_parts) + 1)
            )
        if path_index == len(path_parts):
            return False
        return fnmatchcase(path_parts[path_index], glob_part) and match_from(glob_index + 1, path_index + 1)

    return match_from(0, 0)


class Workbench:
    """A small read-mostly facade around allowlisted project files and commands."""

    def __init__(self, config_dir: Path, logs_dir: Path) -> None:
        self.config_dir = config_dir
        self.logs_dir = logs_dir

    def _config(self) -> WorkbenchConfig:
        # Reloading config per call keeps edits simple and avoids hidden state.
        return load_config(self.config_dir)

    def _project(self, name: str) -> Project:
        config = self._config()
        try:
            return config.projects[name]
        except KeyError as exc:
            raise WorkbenchError(f"Unknown project: {name}") from exc

    def _command(self, name: str) -> AllowedCommand:
        config = self._config()
        try:
            return config.commands[name]
        except KeyError as exc:
            raise WorkbenchError(f"Command is not allowlisted: {name}") from exc

    def log_call(self, tool: str, payload: dict[str, object]) -> None:
        """Append a JSONL audit record to logs/tool-calls.jsonl."""

        self.logs_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool": tool,
            "payload": payload,
        }
        with (self.logs_dir / "tool-calls.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def list_projects(self) -> list[dict[str, str]]:
        self.log_call("list_projects", {})
        return [
            {"name": project.name, "root": str(project.root)}
            for project in self._config().projects.values()
        ]

    def read_project_summary(self, project: str) -> str:
        self.log_call("read_project_summary", {"project": project})
        entry = self._project(project)
        path = safe_relative_path(entry.root, entry.summary_file)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def search_project_notes(self, project: str, query: str) -> list[dict[str, object]]:
        self.log_call("search_project_notes", {"project": project, "query_length": len(query)})
        if not query.strip():
            raise WorkbenchError("Query must be non-empty")

        entry = self._project(project)
        notes_dir = safe_relative_path(entry.root, entry.notes_dir)
        if not notes_dir.exists():
            return []

        results: list[dict[str, object]] = []
        needle = query.casefold()
        for path in sorted(notes_dir.rglob("*")):
            if not path.is_file():
                continue
            try:
                resolved_path = path.resolve()
                resolved_path.relative_to(entry.root)
            except ValueError as exc:
                raise WorkbenchError(f"Note path escapes project root: {path}") from exc
            if path.suffix.lower() not in {".md", ".txt"}:
                continue

            for line_number, line in enumerate(resolved_path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
                if needle in line.casefold():
                    results.append(
                        {
                            "file": str(path.relative_to(entry.root)),
                            "line": line_number,
                            "text": line,
                        }
                    )
        return results

    def search_project_text(self, project: str, query: str, glob: str | None = None) -> list[dict[str, object]]:
        self.log_call(
            "search_project_text",
            {
                "project": project,
                "query_length": len(query),
                "glob": validate_search_glob(glob),
            },
        )
        if not query:
            raise WorkbenchError("Query must be non-empty")

        entry = self._project(project)
        include_glob = validate_search_glob(glob)
        rg_results = self._search_project_text_rg(entry, query, include_glob)
        if rg_results is not None:
            return rg_results
        return self._search_project_text_python(entry, query, include_glob)

    def _search_project_text_rg(
        self,
        project: Project,
        query: str,
        glob: str | None,
    ) -> list[dict[str, object]] | None:
        if which("rg") is None:
            return None

        argv = [
            "rg",
            "--fixed-strings",
            "--line-number",
            "--with-filename",
            "--no-heading",
            "--color",
            "never",
            "--hidden",
            "--glob",
            f"!{project.session_notes_dir}/**",
        ]
        for excluded_glob in RG_EXCLUDE_GLOBS:
            argv.extend(["--glob", excluded_glob])
        if glob is not None:
            argv.extend(["--glob", glob])
        argv.extend(["--", query, "."])

        try:
            result = subprocess.run(
                argv,
                cwd=project.root,
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode == 1:
            return []
        if result.returncode != 0:
            return None

        root = project.root.resolve()
        results: list[dict[str, object]] = []
        for raw_line in result.stdout.splitlines():
            if len(results) >= MAX_TEXT_SEARCH_RESULTS:
                break
            parts = raw_line.split(":", 2)
            if len(parts) != 3:
                continue
            file_text, line_text, text = parts
            try:
                line_number = int(line_text)
            except ValueError:
                continue
            path = safe_relative_path(root, file_text)
            if is_excluded_search_path(path, root, project.session_notes_dir):
                continue
            relative = path.relative_to(root)
            if glob is not None and not matches_search_glob(relative, glob):
                continue
            results.append({"file": str(relative), "line": line_number, "text": text})
        return results

    def _search_project_text_python(self, project: Project, query: str, glob: str | None) -> list[dict[str, object]]:
        root = project.root.resolve()
        results: list[dict[str, object]] = []
        for path in sorted(root.rglob("*")):
            if len(results) >= MAX_TEXT_SEARCH_RESULTS:
                break
            if path.is_dir():
                continue
            if path.is_symlink():
                continue
            resolved_path = path.resolve()
            try:
                resolved_path.relative_to(root)
            except ValueError:
                continue
            if is_excluded_search_path(resolved_path, root, project.session_notes_dir):
                continue
            relative = resolved_path.relative_to(root)
            if glob is not None and not matches_search_glob(relative, glob):
                continue

            try:
                lines = resolved_path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue

            for line_number, line in enumerate(lines, start=1):
                if query in line:
                    results.append(
                        {
                            "file": str(relative),
                            "line": line_number,
                            "text": line,
                        }
                    )
                    if len(results) >= MAX_TEXT_SEARCH_RESULTS:
                        break
        return results

    def git_status(self, project: str) -> str:
        self.log_call("git_status", {"project": project})
        entry = self._project(project)
        return self._run_readonly_git(entry, ["git", "status", "--short"])

    def git_diff(self, project: str) -> str:
        self.log_call("git_diff", {"project": project})
        entry = self._project(project)
        return self._run_readonly_git(entry, ["git", "diff", "--"])

    def _run_readonly_git(self, project: Project, argv: list[str]) -> str:
        env = os.environ.copy()
        env.update(
            {
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "safe.directory",
                "GIT_CONFIG_VALUE_0": str(project.root),
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_PAGER": "cat",
                "PAGER": "cat",
            }
        )
        result = subprocess.run(
            argv,
            cwd=project.root,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            text=True,
            timeout=30,
            env=env,
        )
        output = result.stdout + result.stderr
        if result.returncode != 0:
            raise WorkbenchError(output.strip() or f"Command failed: {' '.join(argv)}")
        return output

    def run_allowed_command(self, project: str, command_name: str) -> dict[str, object]:
        self.log_call("run_allowed_command", {"project": project, "command_name": command_name})
        entry = self._project(project)
        command = self._command(command_name)
        if entry.name not in command.projects:
            raise WorkbenchError(f"Command {command.name!r} is not allowlisted for project: {entry.name}")
        result = subprocess.run(
            list(command.argv),
            cwd=entry.root,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            text=True,
            timeout=120,
        )
        return {
            "command": command.name,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    def save_session_note(self, project: str, note: str) -> dict[str, str]:
        self.log_call("save_session_note", {"project": project, "note_length": len(note)})
        if not note.strip():
            raise WorkbenchError("Note must be non-empty")

        entry = self._project(project)
        notes_dir = safe_relative_path(entry.root, entry.session_notes_dir)
        notes_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = safe_relative_path(entry.root, f"{entry.session_notes_dir}/{timestamp}.md")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"# Session note {timestamp}\n\n{note.strip()}\n")
        return {"path": str(path.relative_to(entry.root))}


def validate_startup_config(config_dir: Path) -> None:
    """Fail fast with a readable error before the MCP server starts."""

    try:
        load_config(config_dir)
    except ConfigError:
        raise
