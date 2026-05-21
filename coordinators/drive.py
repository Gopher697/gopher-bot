from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from coordinators.base import Coordinator


DRIVE_CADENCE_SECONDS = 86400
BUDGET_WARNING_THRESHOLD = 0.80
DRIVE_PRIORITY = 6
DEFAULT_BUDGET_CEILING = 1.00
TIER_COST_ESTIMATES = {1: 0.00, 2: 0.01, 3: 0.10}

# Idle cultivation — Gopher absence threshold before Drive signals cultivation mode.
IDLE_THRESHOLD_SECONDS = 1800           # 30 minutes

# Disk footprint thresholds.
DISK_WARNING_FRACTION = 0.80            # 80% disk used -> warning
DISK_CRITICAL_FRACTION = 0.95           # 95% disk used -> critical

# Drive cadence for cultivation checks (separate from daily commitment check).
CULTIVATION_CADENCE_SECONDS = 900       # check every 15 minutes when idle

_COMMITMENT_ID_PATTERN = re.compile(r"\bC-\d+\b")
_FIELD_NAMES = {"id", "status", "review_trigger"}
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_COMMITMENTS_PATH = _PROJECT_ROOT / "AGENT_COMMITMENTS.md"


@dataclass
class DriveState:
    last_tick: datetime | None = None
    last_bid_content: str | None = None
    session_api_calls: dict[int, int] = field(
        default_factory=lambda: {1: 0, 2: 0, 3: 0}
    )
    session_budget_used: float = 0.0
    budget_ceiling: float = DEFAULT_BUDGET_CEILING
    stalled_commitment_ids: list[str] = field(default_factory=list)
    pending_budget_warning: str | None = None
    # Disk footprint (populated by background_tick via disk_usage_fn).
    disk_total_bytes: int = 0
    disk_used_bytes: int = 0
    disk_free_bytes: int = 0
    # Idle cultivation.
    idle_since_seconds: float | None = None
    last_cultivation_tick: float = 0.0


@dataclass(frozen=True)
class DriveBid:
    coordinator_name: str
    content: str
    priority: int
    timestamp: float
    source: str
    type: str


CommitmentsReader = Callable[[], list[dict]]
Clock = Callable[[], datetime]


class Drive(Coordinator):
    name = "drive"

    def __init__(
        self,
        commitments_reader: CommitmentsReader | None = None,
        clock: Clock | None = None,
        budget_ceiling: float = DEFAULT_BUDGET_CEILING,
        disk_usage_fn: Callable[[], tuple[int, int, int]] | None = None,
    ) -> None:
        self.commitments_reader = commitments_reader or _default_commitments_reader
        self.clock = clock or (lambda: datetime.now(UTC))
        self.state = DriveState(budget_ceiling=budget_ceiling)
        self.disk_usage_fn = disk_usage_fn or _default_disk_usage

    def record_api_call(self, tier: int, cost: float | None = None) -> None:
        tier = int(tier)
        self.state.session_api_calls.setdefault(tier, 0)
        self.state.session_api_calls[tier] += 1
        self.state.session_budget_used += (
            float(cost) if cost is not None else TIER_COST_ESTIMATES.get(tier, 0.0)
        )
        self._update_pending_budget_warning()

    async def background_tick(self, awareness_queue) -> None:
        now = self.clock()
        self.state.last_tick = now

        commitments = self.commitments_reader()
        stalled_ids = _find_stalled_commitment_ids(commitments, now.date())
        self.state.stalled_commitment_ids = stalled_ids

        try:
            total, used, free = self.disk_usage_fn()
            self.state.disk_total_bytes = int(total)
            self.state.disk_used_bytes = int(used)
            self.state.disk_free_bytes = int(free)
        except Exception:
            pass

        self._update_pending_budget_warning()
        observation = _build_observation(
            stalled_ids,
            self.state.pending_budget_warning,
        )
        cultivation_note = _build_cultivation_note(self.state, now)
        if cultivation_note:
            observation = f"{observation} {cultivation_note}".strip()
            self.state.last_cultivation_tick = time.time()
        if not observation:
            return
        if observation == self.state.last_bid_content:
            return

        _submit_drive_bid(awareness_queue, observation)
        self.state.last_bid_content = observation

    def process(self, packet: dict) -> dict:
        if "model_tier" in packet:
            self.record_api_call(int(packet["model_tier"]))

        time_since_last = packet.get("time_since_last_interaction", 0)
        if (
            isinstance(time_since_last, (int, float))
            and time_since_last > IDLE_THRESHOLD_SECONDS
        ):
            if self.state.idle_since_seconds is None:
                self.state.idle_since_seconds = float(time_since_last)
        else:
            self.state.idle_since_seconds = None

        packet["drive_budget_status"] = {
            "session_budget_used": round(self.state.session_budget_used, 4),
            "budget_ceiling": self.state.budget_ceiling,
            "budget_fraction": round(_budget_fraction(self.state), 4),
            "api_calls_by_tier": dict(self.state.session_api_calls),
            "disk_total_bytes": self.state.disk_total_bytes,
            "disk_used_bytes": self.state.disk_used_bytes,
            "disk_free_bytes": self.state.disk_free_bytes,
            "disk_fraction": _disk_fraction(self.state),
            "idle_since_seconds": self.state.idle_since_seconds,
        }
        return packet

    def _update_pending_budget_warning(self) -> None:
        if _budget_fraction(self.state) >= BUDGET_WARNING_THRESHOLD:
            self.state.pending_budget_warning = _format_budget_warning(self.state)
        else:
            self.state.pending_budget_warning = None


def _default_commitments_reader() -> list[dict]:
    try:
        text = _COMMITMENTS_PATH.read_text(encoding="utf-8")
    except OSError:
        return []

    commitments: list[dict] = []
    current: dict | None = None
    in_table = False

    for line in text.splitlines():
        heading_match = _COMMITMENT_ID_PATTERN.search(line)
        if line.startswith("### ") and heading_match:
            if current:
                commitments.append(current)
            current = {"id": heading_match.group(0)}
            in_table = False
            continue

        if "|" not in line:
            if in_table and current:
                commitments.append(current)
                current = None
            in_table = False
            continue

        cells = [_clean_cell(cell) for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue

        key, value = cells[0], cells[1]
        if key == "Field" or set(line.strip()) <= {"|", "-", " "}:
            continue

        if key == "id":
            id_match = _COMMITMENT_ID_PATTERN.search(value)
            if id_match:
                if current and current.get("id") != id_match.group(0):
                    commitments.append(current)
                current = current or {}
                current["id"] = id_match.group(0)
                in_table = True
            continue

        if current is not None and key in _FIELD_NAMES:
            current[key] = value
            in_table = True

    if current:
        commitments.append(current)

    return [
        {
            "id": item.get("id", ""),
            "status": item.get("status", ""),
            "review_trigger": item.get("review_trigger", ""),
        }
        for item in commitments
        if str(item.get("status", "")).lower() == "active"
    ]


def _default_disk_usage() -> tuple[int, int, int]:
    import shutil

    try:
        usage = shutil.disk_usage(".")
        return usage.total, usage.used, usage.free
    except OSError:
        return 0, 0, 0


def _find_stalled_commitment_ids(
    commitments: list[dict],
    today: date,
) -> list[str]:
    stalled: list[str] = []
    for commitment in commitments:
        if str(commitment.get("status", "")).lower() != "active":
            continue
        trigger_date = _parse_review_trigger_date(commitment.get("review_trigger"))
        if trigger_date is not None and trigger_date < today:
            commitment_id = str(commitment.get("id", "")).strip()
            if commitment_id:
                stalled.append(commitment_id)
    return stalled


def _parse_review_trigger_date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def _build_observation(
    stalled_ids: list[str],
    budget_warning: str | None,
) -> str:
    parts: list[str] = []
    if stalled_ids:
        ids = ", ".join(stalled_ids)
        noun = "trigger has" if len(stalled_ids) == 1 else "triggers have"
        parts.append(f"{ids} review {noun} passed — flagging for awareness")
    if budget_warning:
        parts.append(budget_warning)
    return " ".join(parts)


def _build_cultivation_note(state: DriveState, now: datetime) -> str:
    import time as _time

    if state.idle_since_seconds is None:
        return ""
    elapsed_since_last = _time.time() - state.last_cultivation_tick
    if elapsed_since_last < CULTIVATION_CADENCE_SECONDS:
        return ""
    idle_minutes = int(state.idle_since_seconds // 60)
    disk_pct = _disk_fraction(state)
    disk_status = (
        "critical" if disk_pct >= DISK_CRITICAL_FRACTION
        else "warning" if disk_pct >= DISK_WARNING_FRACTION
        else "ok"
    )
    used_gb = state.disk_used_bytes / 1_073_741_824
    free_gb = state.disk_free_bytes / 1_073_741_824
    return (
        f"[cultivation mode] idle {idle_minutes}m; "
        f"disk {used_gb:.1f}GB used / {free_gb:.1f}GB free (status={disk_status})"
    )


def _format_budget_warning(state: DriveState) -> str:
    fraction = _budget_fraction(state)
    return (
        f"API budget is at {fraction:.0%} of the session ceiling "
        f"(${state.session_budget_used:.2f} of ${state.budget_ceiling:.2f})"
    )


def _budget_fraction(state: DriveState) -> float:
    if state.budget_ceiling <= 0:
        return 0.0
    return state.session_budget_used / state.budget_ceiling


def _disk_fraction(state: DriveState) -> float:
    if state.disk_total_bytes == 0:
        return 0.0
    return round(state.disk_used_bytes / state.disk_total_bytes, 4)


def _submit_drive_bid(awareness_queue, observation: str) -> None:
    bid = DriveBid(
        coordinator_name="drive",
        source="drive",
        priority=DRIVE_PRIORITY,
        content=observation,
        type="progress_check",
        timestamp=time.time(),
    )
    submit = getattr(awareness_queue, "submit", None)
    if callable(submit):
        submit(bid)
        return

    put_nowait = getattr(awareness_queue, "put_nowait", None)
    if callable(put_nowait):
        put_nowait(bid)
        return

    raise TypeError("awareness_queue must expose submit() or put_nowait()")


def _clean_cell(value: str) -> str:
    return value.replace("`", "").replace("~", "").strip()
