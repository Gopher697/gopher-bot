"""
Wisdom — long-horizon temporal interpretation.

Background-only coordinator. Wisdom compares structured history across time and
submits proposal bids when recurring signals deserve Awareness review. It does not
write directly to the graph or call an LLM.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from coordinators.base import PROJECT_ROOT, Coordinator
from coordinators.bid import PRIORITY_PATTERN, BidQueue


WISDOM_CADENCE_SECONDS = 604800   # weekly default
WISDOM_TURN_WINDOW = 200
WISDOM_RESEARCH_WINDOW = 50
WISDOM_PATTERN_WINDOW = 20
WISDOM_RECURRENCE_THRESHOLD = 2   # pattern must appear >= this many times to count
WISDOM_LOG_DIR = PROJECT_ROOT / "logs" / "wisdom"
WISDOM_STATE_PATH = PROJECT_ROOT / "world_models" / "wisdom_state.json"

_ARCHIVIST_RESEARCH_LOG_PATH = (
    PROJECT_ROOT / "logs" / "archivist" / "research.jsonl"
)
_PATTERN_MONITOR_LOG_PATH = PROJECT_ROOT / "logs" / "pattern_monitor.jsonl"
_RESOLVED_STATUSES = {"resolved", "complete", "completed", "closed"}


JsonEntryReader = Callable[[int], list[dict[str, Any]]]
WisdomHistoryReader = Callable[[int], list[dict[str, Any]]]
ObservationLogWriter = Callable[[dict[str, Any]], None]
Clock = Callable[[], datetime]


@dataclass
class WisdomState:
    last_tick: datetime | None = None
    last_insight: str = ""
    insight_count: int = 0


StateLoader = Callable[[], WisdomState]
StateSaver = Callable[[WisdomState], None]


@dataclass(frozen=True)
class WisdomBid:
    coordinator_name: str
    content: str
    priority: int
    timestamp: float
    source: str = "wisdom"
    type: str = "historical_insight"


class Wisdom(Coordinator):
    name = "wisdom"

    def __init__(
        self,
        turn_log_reader: JsonEntryReader | None = None,
        research_log_reader: JsonEntryReader | None = None,
        pattern_log_reader: JsonEntryReader | None = None,
        learning_episode_reader: JsonEntryReader | None = None,
        wisdom_history_reader: WisdomHistoryReader | None = None,
        observation_log_writer: ObservationLogWriter | None = None,
        clock: Clock | None = None,
        state: WisdomState | None = None,
        _load_state_fn: StateLoader | None = None,
        _save_state_fn: StateSaver | None = None,
        cadence_seconds: int = WISDOM_CADENCE_SECONDS,
        turn_window: int = WISDOM_TURN_WINDOW,
        research_window: int = WISDOM_RESEARCH_WINDOW,
        pattern_window: int = WISDOM_PATTERN_WINDOW,
    ) -> None:
        self.turn_log_reader = turn_log_reader or _default_turn_log_reader
        self.research_log_reader = research_log_reader or _default_research_log_reader
        self.pattern_log_reader = pattern_log_reader or _default_pattern_log_reader
        self.learning_episode_reader = (
            learning_episode_reader or _default_learning_episode_reader
        )
        self.clock = clock or (lambda: datetime.now(UTC))
        self.wisdom_history_reader = wisdom_history_reader or (
            lambda days: _read_wisdom_observation_entries(days, clock=self.clock)
        )
        self.observation_log_writer = (
            observation_log_writer or _append_wisdom_observation_log_entry
        )
        self.cadence_seconds = int(cadence_seconds)
        self.turn_window = int(turn_window)
        self.research_window = int(research_window)
        self.pattern_window = int(pattern_window)
        self._save_state_fn = _save_state_fn or _save_state
        self.state = state if state is not None else (_load_state_fn or _load_state)()

    def process(self, packet: dict) -> dict:
        return packet

    async def background_tick(self, bid_queue: BidQueue) -> None:
        now = self.clock()
        if not self._cadence_due(now):
            return
        self._run_analysis_tick(bid_queue, now)

    def maybe_trigger(self, bid_queue: BidQueue, recent_bid: Any) -> None:
        if not _is_pattern_monitor_system_bid(recent_bid):
            return

        pattern = _bid_pattern_text(recent_bid)
        if not pattern:
            return

        history = _safe_read(lambda: self.wisdom_history_reader(30), [])
        if not _history_contains_pattern(pattern, history):
            return

        self._run_analysis_tick(
            bid_queue,
            self.clock(),
            triggered_pattern=pattern,
        )

    def analyze_belief_doctrine_arc(self) -> dict[str, Any]:
        return {
            "available": False,
            "reason": (
                "Claim/Belief/Doctrine arc analysis is deferred until "
                "Archivist claim extraction is wired in T-71."
            ),
        }

    def _cadence_due(self, now: datetime) -> bool:
        if self.state.last_tick is None:
            return True
        return _seconds_between(self.state.last_tick, now) >= self.cadence_seconds

    def _run_analysis_tick(
        self,
        bid_queue: BidQueue,
        now: datetime,
        triggered_pattern: str = "",
    ) -> None:
        turns = _safe_read(lambda: self.turn_log_reader(self.turn_window), [])
        research_entries = _safe_read(
            lambda: self.research_log_reader(self.research_window),
            [],
        )
        pattern_entries = _safe_read(
            lambda: self.pattern_log_reader(self.pattern_window),
            [],
        )
        learning_episodes = _safe_read(
            lambda: self.learning_episode_reader(self.research_window),
            [],
        )

        analysis = _analyze_history(
            turns,
            research_entries,
            pattern_entries,
            learning_episodes,
            triggered_pattern=triggered_pattern,
        )
        bid_submitted = False
        if analysis["insight"]:
            _submit_wisdom_bid(bid_queue, analysis["insight"], now)
            bid_submitted = True
            self.state.last_insight = analysis["insight"]
            self.state.insight_count += 1

        observation = {
            "timestamp": now.isoformat(),
            "turn_window_size": analysis["turn_window_size"],
            "accuracy_mean": analysis["accuracy_mean"],
            "accuracy_trend": analysis["accuracy_trend"],
            "recurring_goals": analysis["recurring_goals"],
            "pattern_monitor_recurrences": analysis[
                "pattern_monitor_recurrences"
            ],
            "insight": analysis["insight"],
            "bid_submitted": bid_submitted,
        }
        _safe_write(self.observation_log_writer, observation)
        self.state.last_tick = now
        self._save_state_fn(self.state)


def _analyze_history(
    turns: list[dict[str, Any]],
    research_entries: list[dict[str, Any]],
    pattern_entries: list[dict[str, Any]],
    learning_episodes: list[dict[str, Any]],
    *,
    triggered_pattern: str = "",
) -> dict[str, Any]:
    turn_analysis = _analyze_turns(turns)
    research_goals = _recurring_research_goals(research_entries)
    learning_goals = _recurring_learning_episode_goals(learning_episodes)
    recurring_goals = _merge_unique(
        turn_analysis["recurring_goals"],
        research_goals,
        learning_goals,
    )
    pattern_recurrences, pattern_counts = _pattern_monitor_recurrences(
        pattern_entries,
    )

    if triggered_pattern and not _contains_text(pattern_recurrences, triggered_pattern):
        pattern_recurrences = [*pattern_recurrences, triggered_pattern]
        pattern_counts[triggered_pattern] = max(
            WISDOM_RECURRENCE_THRESHOLD,
            pattern_counts.get(triggered_pattern, 0),
        )

    insight = _assemble_insight(
        turn_window_size=turn_analysis["turn_window_size"],
        accuracy_count=turn_analysis["accuracy_count"],
        accuracy_trend=turn_analysis["accuracy_trend"],
        accuracy_start=turn_analysis["accuracy_start"],
        accuracy_end=turn_analysis["accuracy_end"],
        recurring_goals=recurring_goals,
        error_count=turn_analysis["error_count"],
        pattern_recurrences=pattern_recurrences,
        pattern_counts=pattern_counts,
        triggered_pattern=triggered_pattern,
    )

    return {
        "turn_window_size": turn_analysis["turn_window_size"],
        "accuracy_mean": turn_analysis["accuracy_mean"],
        "accuracy_trend": turn_analysis["accuracy_trend"],
        "recurring_goals": recurring_goals,
        "pattern_monitor_recurrences": pattern_recurrences,
        "insight": insight,
    }


def _analyze_turns(turns: list[dict[str, Any]]) -> dict[str, Any]:
    accuracies = [
        value
        for value in (_optional_float(turn.get("last_prediction_accuracy")) for turn in turns)
        if value is not None
    ]
    accuracy_mean = round(_mean(accuracies), 3) if accuracies else 0.0
    accuracy_start, accuracy_end = _accuracy_halves(accuracies)
    accuracy_trend = _accuracy_trend(accuracy_start, accuracy_end)
    goals = [
        str(turn.get("orientation_active_goal") or "").strip()
        for turn in turns
    ]

    return {
        "turn_window_size": len(turns),
        "accuracy_count": len(accuracies),
        "accuracy_mean": accuracy_mean,
        "accuracy_start": accuracy_start,
        "accuracy_end": accuracy_end,
        "accuracy_trend": accuracy_trend,
        "recurring_goals": _recurring_texts(goals),
        "error_count": sum(1 for turn in turns if bool(turn.get("has_error"))),
    }


def _accuracy_halves(accuracies: list[float]) -> tuple[float, float]:
    if not accuracies:
        return 0.0, 0.0
    if len(accuracies) == 1:
        return accuracies[0], accuracies[0]
    midpoint = len(accuracies) // 2
    first = accuracies[:midpoint]
    second = accuracies[midpoint:]
    return _mean(first), _mean(second)


def _accuracy_trend(start: float, end: float) -> str:
    delta = end - start
    if delta > 0.001:
        return "up"
    if delta < -0.001:
        return "down"
    return "stable"


def _recurring_research_goals(entries: list[dict[str, Any]]) -> list[str]:
    goals = []
    for entry in entries:
        if _is_resolved(entry.get("status")):
            continue
        goal = str(entry.get("active_goal") or "").strip()
        if goal:
            goals.append(goal)
    return _recurring_texts(goals)


def _recurring_learning_episode_goals(entries: list[dict[str, Any]]) -> list[str]:
    goals = []
    for entry in entries:
        goal = str(
            entry.get("active_goal")
            or entry.get("goal")
            or entry.get("summary")
            or ""
        ).strip()
        if goal:
            goals.append(goal)
    return _recurring_texts(goals)


def _pattern_monitor_recurrences(
    entries: list[dict[str, Any]],
) -> tuple[list[str], dict[str, int]]:
    descriptions = [_pattern_description(entry) for entry in entries]
    recurrences = _recurring_texts(descriptions)
    counts = _text_counts(descriptions)
    return recurrences, counts


def _assemble_insight(
    *,
    turn_window_size: int,
    accuracy_count: int,
    accuracy_trend: str,
    accuracy_start: float,
    accuracy_end: float,
    recurring_goals: list[str],
    error_count: int,
    pattern_recurrences: list[str],
    pattern_counts: dict[str, int],
    triggered_pattern: str = "",
) -> str:
    parts: list[str] = []

    if accuracy_count > 0:
        parts.append(
            "Accuracy trend: "
            f"{accuracy_trend.upper()} "
            f"({accuracy_start:.2f} -> {accuracy_end:.2f} "
            f"over {turn_window_size} turns)."
        )

    if recurring_goals:
        goals = ", ".join(f"'{goal}'" for goal in recurring_goals[:3])
        noun = "goal" if len(recurring_goals) == 1 else "goals"
        parts.append(f"Recurring {noun}: {goals}.")

    if error_count > 0:
        noun = "entry" if error_count == 1 else "entries"
        parts.append(f"Errors observed: {error_count} {noun}.")

    for pattern in pattern_recurrences[:3]:
        count = pattern_counts.get(pattern, WISDOM_RECURRENCE_THRESHOLD)
        parts.append(f"Pattern Monitor flagged '{pattern}' {count} times.")

    if triggered_pattern:
        parts.append(
            "Pattern Monitor signal recurred from Wisdom history: "
            f"'{triggered_pattern}'."
        )

    return " ".join(parts).strip()


def _submit_wisdom_bid(
    bid_queue: BidQueue,
    insight: str,
    now: datetime,
) -> None:
    bid = WisdomBid(
        coordinator_name="wisdom",
        content=insight,
        priority=PRIORITY_PATTERN,
        timestamp=now.timestamp(),
    )
    submit = getattr(bid_queue, "submit", None)
    if callable(submit):
        submit(bid)
        return

    put_nowait = getattr(bid_queue, "put_nowait", None)
    if callable(put_nowait):
        put_nowait(bid)


def _default_turn_log_reader(limit: int) -> list[dict[str, Any]]:
    from coordinators.base import read_turn_log_entries

    return read_turn_log_entries(limit=limit)


def _default_research_log_reader(limit: int) -> list[dict[str, Any]]:
    return _read_jsonl_entries(_ARCHIVIST_RESEARCH_LOG_PATH, limit)


def _default_pattern_log_reader(limit: int) -> list[dict[str, Any]]:
    return _read_jsonl_entries(_PATTERN_MONITOR_LOG_PATH, limit)


def _default_learning_episode_reader(limit: int) -> list[dict[str, Any]]:
    driver = None
    graph_module = None
    try:
        from world_models import config, graph

        graph_module = graph
        driver = graph.connect()
        with driver.session(database=config.NEO4J_DATABASE) as session:
            records = session.run(
                """
                MATCH (episode:LearningEpisode)
                RETURN properties(episode) AS properties
                ORDER BY episode.created_at DESC
                LIMIT $limit
                """,
                limit=int(limit),
            )
            return [dict(record["properties"]) for record in records]
    except Exception:
        return []
    finally:
        if driver is not None and graph_module is not None:
            try:
                graph_module.close(driver)
            except Exception:
                pass


def _read_jsonl_entries(path: Path, limit: int) -> list[dict[str, Any]]:
    limit = int(limit)
    if limit <= 0:
        return []

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    entries: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            entries.append(item)
    return entries


def _load_state() -> WisdomState:
    try:
        raw = json.loads(WISDOM_STATE_PATH.read_text(encoding="utf-8"))
        last_tick_raw = raw.get("last_tick") if isinstance(raw, dict) else None
        last_tick = (
            datetime.fromisoformat(str(last_tick_raw))
            if last_tick_raw
            else None
        )
        return WisdomState(last_tick=last_tick)
    except Exception:
        return WisdomState()


def _save_state(state: WisdomState) -> None:
    try:
        WISDOM_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        WISDOM_STATE_PATH.write_text(
            json.dumps(
                {
                    "last_tick": (
                        state.last_tick.isoformat()
                        if state.last_tick is not None
                        else None
                    ),
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    except OSError:
        return


def _append_wisdom_observation_log_entry(
    entry: dict[str, Any],
    log_dir: Path = WISDOM_LOG_DIR,
) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{_entry_date(entry):%Y%m%d}.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True, default=str) + "\n")


def _read_wisdom_observation_entries(
    days: int,
    log_dir: Path = WISDOM_LOG_DIR,
    clock: Clock | None = None,
) -> list[dict[str, Any]]:
    now = (clock or (lambda: datetime.now(UTC)))()
    cutoff = (now - timedelta(days=int(days))).date()
    entries: list[dict[str, Any]] = []
    try:
        paths = sorted(log_dir.glob("*.jsonl"))
    except OSError:
        return []

    for path in paths:
        try:
            path_date = datetime.strptime(path.stem, "%Y%m%d").date()
        except ValueError:
            continue
        if path_date < cutoff:
            continue
        entries.extend(_read_jsonl_entries(path, 10000))
    return entries


def _history_contains_pattern(
    pattern: str,
    entries: list[dict[str, Any]],
) -> bool:
    for entry in entries:
        recurrences = entry.get("pattern_monitor_recurrences") or []
        if isinstance(recurrences, list):
            for item in recurrences:
                if _same_text(pattern, str(item)):
                    return True
        if _same_text(pattern, str(entry.get("insight") or "")):
            return True
    return False


def _pattern_description(entry: dict[str, Any]) -> str:
    for key in ("description", "pattern", "content", "reasoning_trace", "type"):
        value = str(entry.get(key) or "").strip()
        if value:
            return _clean_pattern_text(value)
    return ""


def _clean_pattern_text(value: str) -> str:
    value = " ".join(value.split())
    if value.lower().startswith("pattern:"):
        value = value.split(":", 1)[1].strip()
    return value


def _recurring_texts(values: list[str]) -> list[str]:
    counts = _text_counts(values)
    return [
        text
        for text, count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0].lower()),
        )
        if count >= WISDOM_RECURRENCE_THRESHOLD
    ]


def _text_counts(values: list[str]) -> dict[str, int]:
    display_by_normalized: dict[str, str] = {}
    counter: Counter[str] = Counter()
    for value in values:
        cleaned = " ".join(str(value or "").split())
        if not cleaned:
            continue
        normalized = cleaned.lower()
        display_by_normalized.setdefault(normalized, cleaned)
        counter[normalized] += 1
    return {
        display_by_normalized[key]: count
        for key, count in counter.items()
    }


def _merge_unique(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    for group in groups:
        for value in group:
            if not _contains_text(merged, value):
                merged.append(value)
    return merged


def _contains_text(values: list[str], target: str) -> bool:
    return any(_same_text(value, target) for value in values)


def _same_text(left: str, right: str) -> bool:
    left_norm = " ".join(str(left or "").lower().split())
    right_norm = " ".join(str(right or "").lower().split())
    if not left_norm or not right_norm:
        return False
    return left_norm == right_norm or left_norm in right_norm or right_norm in left_norm


def _is_pattern_monitor_system_bid(recent_bid: Any) -> bool:
    bid_type = str(getattr(recent_bid, "type", "") or "").strip()
    if bid_type != "system_pattern":
        return False

    source = str(getattr(recent_bid, "source", "") or "").strip()
    coordinator = str(getattr(recent_bid, "coordinator_name", "") or "").strip()
    return source == "pattern_monitor" or coordinator == "pattern_monitor"


def _bid_pattern_text(recent_bid: Any) -> str:
    for attr in ("description", "pattern", "content"):
        value = str(getattr(recent_bid, attr, "") or "").strip()
        if value:
            return _clean_pattern_text(value)
    return ""


def _entry_date(entry: dict[str, Any]) -> datetime:
    value = str(entry.get("timestamp") or "").strip()
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.now(UTC)


def _safe_read(func: Callable[[], list[dict[str, Any]]], default: list[dict[str, Any]]):
    try:
        result = func()
    except Exception:
        return default
    return result if isinstance(result, list) else default


def _safe_write(writer: ObservationLogWriter, entry: dict[str, Any]) -> None:
    try:
        writer(entry)
    except Exception:
        return


def _is_resolved(status: Any) -> bool:
    return str(status or "").strip().lower() in _RESOLVED_STATUSES


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _seconds_between(start: datetime, end: datetime) -> float:
    try:
        return (end - start).total_seconds()
    except TypeError:
        return end.timestamp() - start.timestamp()
