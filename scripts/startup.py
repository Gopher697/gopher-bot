from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Optional, TextIO


WORKBENCH_ROOT = Path(r"D:\Gopher Bot\gopher-bot")
PROJECT_NAME = "gopher-bot"

if str(WORKBENCH_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKBENCH_ROOT))


@dataclass
class CharterInfo:
    status: str = "unknown"
    version: str = "unknown"


@dataclass
class Commitment:
    id: str
    status: str
    description: str


@dataclass
class StartupState:
    incomplete_reasons: list
    warnings: list

    @property
    def complete(self) -> bool:
        return not self.incomplete_reasons

    def warn(self, message: str, reason: Optional[str] = None) -> None:
        self.warnings.append(message)
        if reason:
            self.incomplete_reasons.append(reason)


def read_text(path: Path, state: StartupState, reason: str) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        state.warn(f"WARNING: missing {path.name}", reason)
        return None
    except OSError as exc:
        state.warn(f"WARNING: could not read {path}: {exc}", reason)
        return None


def parse_header_value(text: str, field: str) -> Optional[str]:
    pattern = rf"^\*\*{re.escape(field)}:\*\*\s*(.+?)\s*$"
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        return None
    return match.group(1).strip()


def read_charter(root: Path, state: StartupState) -> CharterInfo:
    path = root / "AGENT_CHARTER.md"
    text = read_text(path, state, "missing AGENT_CHARTER.md")
    if text is None:
        return CharterInfo()

    status = parse_header_value(text, "Status")
    version = parse_header_value(text, "Version")
    if status is None:
        state.warn(
            "WARNING: AGENT_CHARTER.md is missing a Status header",
            "charter status missing",
        )
        status = "unknown"
    if version is None:
        state.warn(
            "WARNING: AGENT_CHARTER.md is missing a Version header",
            "charter version missing",
        )
        version = "unknown"
    if "Ratified" not in status:
        state.warn(
            "WARNING: AGENT_CHARTER.md Status does not contain Ratified",
            "charter not ratified",
        )

    return CharterInfo(status=status, version=version)


def parse_table_fields(text: str) -> dict:
    fields = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "`" not in stripped:
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue
        key = cells[0].strip("`").strip().lower()
        value = cells[1].strip()
        if key not in fields:
            fields[key] = value
    return fields


def parse_commitments(text: str) -> list:
    matches = list(re.finditer(r"^###\s+(C-\d+)\b.*$", text, flags=re.MULTILINE))
    commitments = []

    for index, match in enumerate(matches):
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        fields = parse_table_fields(text[body_start:body_end])
        commitment_id = fields.get("id", match.group(1))
        status = fields.get("status", "unknown").strip().lower()
        description = fields.get("description", "").strip()
        commitments.append(
            Commitment(id=commitment_id, status=status, description=description)
        )

    return commitments


def read_commitments(root: Path, state: StartupState) -> list:
    path = root / "AGENT_COMMITMENTS.md"
    text = read_text(path, state, "missing AGENT_COMMITMENTS.md")
    if text is None:
        return []
    return parse_commitments(text)


def query_world_model_summary() -> str:
    try:
        from world_models import config, graph, vector_index

        driver = graph.connect()
        try:
            vector_index.ensure_vector_index(driver, config.NEO4J_DATABASE)
            entities = graph.query_environment(driver, "global")
        finally:
            graph.close(driver)
    except Exception:
        return "WARNING — Neo4j not reachable"

    entity_count = len(entities)
    noun = "entity" if entity_count == 1 else "entities"
    return f"{entity_count} {noun} in global ✓"


def scan_pending_proposals(root: Path, state: StartupState) -> list:
    pending_dir = root / "proposals" / "pending"
    if not pending_dir.exists():
        state.warn(
            "WARNING: proposals/pending/ not found",
            "missing proposals/pending/",
        )
        return []
    return sorted(
        path.name
        for path in pending_dir.glob("*.md")
        if path.is_file() and path.name != ".gitkeep"
    )


def read_autonomy_level(root: Path) -> str:
    path = root / "AUTONOMY_LEVELS.md"
    if not path.exists():
        return "Tier 2 default (no global file found)"

    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped == "---":
                continue
            return stripped
    except OSError as exc:
        return f"unreadable AUTONOMY_LEVELS.md ({exc})"

    return "Tier 2 default (no autonomy line found)"


def result_text(state: StartupState) -> str:
    if state.complete:
        return "COMPLETE"
    return "INCOMPLETE — " + ", ".join(state.incomplete_reasons)


def append_action_log(root: Path, now: datetime, state: StartupState) -> tuple:
    date_slug = now.strftime("%Y%m%d")
    date_text = now.strftime("%Y-%m-%d")
    rel_path = Path("logs") / "actions" / f"{date_slug}.md"
    path = root / rel_path
    display_path = rel_path.as_posix()

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(
                "\n".join(
                    [
                        f"# Action Log — {date_text}",
                        f"**Project:** {PROJECT_NAME}",
                        f"**WORKBENCH_ROOT:** {root}",
                        "---",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
        with path.open("a", encoding="utf-8") as handle:
            iso_timestamp = now.isoformat(timespec="seconds")
            handle.write(
                "\n".join(
                    [
                        f"### [{iso_timestamp}] — Coordinator startup",
                        "| Field | Value |",
                        "|---|---|",
                        f"| timestamp | {iso_timestamp} |",
                        "| agent | startup.py |",
                        "| action | Article IX startup sequence executed |",
                        "| authority | Tier 3 (startup log append) |",
                        f"| files_changed | {display_path} (appended) |",
                        f"| result | {result_text(state)} |",
                        "| rollback_note | n/a |",
                        "",
                        "",
                    ]
                )
            )
    except OSError as exc:
        state.warn(f"WARNING: could not append action log {path}: {exc}", "action log append failed")
        return display_path, False

    return display_path, True


def commitment_summary(commitments: Iterable[Commitment]) -> tuple:
    items = list(commitments)
    active_count = sum(1 for item in items if item.status == "active")
    blocked_count = sum(1 for item in items if item.status == "blocked")
    return active_count, blocked_count, items


def print_report(
    *,
    out: TextIO,
    now: datetime,
    charter: CharterInfo,
    commitments: list,
    world_model_summary: str,
    pending_proposals: list,
    autonomy_level: str,
    action_log_path: str,
    action_log_ok: bool,
    state: StartupState,
) -> None:
    active_count, blocked_count, commitment_items = commitment_summary(commitments)
    checkmark = "✓"
    separator = "=" * 60

    print(separator, file=out)
    print("COORDINATOR STARTUP — Article IX", file=out)
    print(separator, file=out)
    print(now.isoformat(timespec="seconds"), file=out)
    print("", file=out)

    charter_marker = checkmark if "Ratified" in charter.status else "WARNING"
    print(f"[1] Charter .............. {charter.status} {charter_marker}", file=out)
    if charter.version != "unknown":
        print(f"      Version: {charter.version}", file=out)

    print(
        f"[2] Commitments .......... {active_count} active, {blocked_count} blocked",
        file=out,
    )
    for commitment in commitment_items:
        suffix = "" if commitment.status == "active" else f" ({commitment.status})"
        print(f"      {commitment.id}  {commitment.description}{suffix}", file=out)

    print(f"[3] World models ......... {world_model_summary}", file=out)

    pending_marker = checkmark if not pending_proposals else ""
    print(
        f"[4] Pending proposals .... {len(pending_proposals)} {pending_marker}".rstrip(),
        file=out,
    )
    if pending_proposals:
        for name in pending_proposals:
            print(f"      {name}", file=out)
    else:
        print("      No pending proposals.", file=out)

    print(f"[5] Autonomy level ....... {autonomy_level}", file=out)

    log_marker = checkmark if action_log_ok else "WARNING"
    print(f"[6] Action log ........... opened {action_log_path} {log_marker}", file=out)

    if state.warnings:
        print("", file=out)
        for warning in state.warnings:
            print(warning, file=out)

    print(separator, file=out)
    if state.complete:
        print("Status: READY", file=out)
    else:
        print(f"Status: INCOMPLETE — {', '.join(state.incomplete_reasons)}", file=out)
    print(separator, file=out)


def run_startup(
    root: Path = WORKBENCH_ROOT,
    now: Optional[datetime] = None,
    out: TextIO = sys.stdout,
    world_model_summary_fn: Callable[[], str] | None = None,
) -> int:
    root = Path(root)
    timestamp = now or datetime.now().replace(microsecond=0)
    state = StartupState(incomplete_reasons=[], warnings=[])
    summary_fn = world_model_summary_fn or query_world_model_summary

    charter = read_charter(root, state)
    commitments = read_commitments(root, state)
    world_model_summary = summary_fn()
    pending_proposals = scan_pending_proposals(root, state)
    autonomy_level = read_autonomy_level(root)
    action_log_path, action_log_ok = append_action_log(root, timestamp, state)

    print_report(
        out=out,
        now=timestamp,
        charter=charter,
        commitments=commitments,
        world_model_summary=world_model_summary,
        pending_proposals=pending_proposals,
        autonomy_level=autonomy_level,
        action_log_path=action_log_path,
        action_log_ok=action_log_ok,
        state=state,
    )

    return 0 if state.complete else 1


def main() -> int:
    return run_startup()


if __name__ == "__main__":
    sys.exit(main())
