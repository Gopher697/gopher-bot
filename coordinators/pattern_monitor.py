"""
Pattern Monitor — default mode network.

Runs on a slow cadence (90s). Watches coordinator activity logs and the knowledge
graph for longitudinal patterns. Submits bids to Awareness when something significant
is found. Does not react to individual events — it looks across history.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any

from coordinators.base import (
    PROJECT_ROOT,
    Coordinator,
    read_coordinator_log_entries,
)
from coordinators.bid import Bid, BidQueue, PRIORITY_PATTERN


DEFAULT_LOG_LIMIT = 50
ACCEPTANCE_WINDOW = 20
ACCEPTANCE_DROP_THRESHOLD = 0.3
REASONING_REPEAT_THRESHOLD = 3
GOD_NODE_DEGREE_THRESHOLD = 10
GOD_NODE_LOG_LIMIT = 5
TRAINING_CANDIDATE_LIMIT = 100
PATTERN_MONITOR_LOG_PATH = PROJECT_ROOT / "logs" / "pattern_monitor.jsonl"


CoordinatorLogReader = Callable[[int], list[dict[str, Any]]]
TrainingCandidateReader = Callable[[], list[dict[str, Any]]]
TrainingCandidateWriter = Callable[[str, float], None]
GodNodeReader = Callable[[int, int], list[dict[str, Any]]]
PatternLogWriter = Callable[[dict[str, Any]], None]


class PatternMonitor(Coordinator):
    name = "pattern_monitor"

    def __init__(
        self,
        coordinator_log_reader: CoordinatorLogReader | None = None,
        training_candidate_reader: TrainingCandidateReader | None = None,
        training_candidate_writer: TrainingCandidateWriter | None = None,
        god_node_reader: GodNodeReader | None = None,
        pattern_log_writer: PatternLogWriter | None = None,
        time_fn: Callable[[], float] = time.time,
        log_limit: int = DEFAULT_LOG_LIMIT,
        acceptance_window: int = ACCEPTANCE_WINDOW,
        god_node_degree_threshold: int = GOD_NODE_DEGREE_THRESHOLD,
    ) -> None:
        self.coordinator_log_reader = (
            coordinator_log_reader or read_coordinator_log_entries
        )
        self.training_candidate_reader = (
            training_candidate_reader or _default_training_candidate_reader
        )
        self.training_candidate_writer = (
            training_candidate_writer or _default_training_candidate_writer
        )
        self.god_node_reader = god_node_reader or _default_god_node_reader
        self.pattern_log_writer = pattern_log_writer or _append_pattern_log_entry
        self.time_fn = time_fn
        self.log_limit = int(log_limit)
        self.acceptance_window = int(acceptance_window)
        self.god_node_degree_threshold = int(god_node_degree_threshold)

    def process(self, packet: dict) -> dict:
        return packet

    async def background_tick(self, bid_queue: BidQueue) -> None:
        try:
            logs = self.coordinator_log_reader(self.log_limit)
        except Exception as exc:
            logs = []
            self._log_error("read_coordinator_logs", exc)

        self._run_pass("acceptance_rate", self._scan_acceptance_rates, logs, bid_queue)
        self._run_pass(
            "reasoning_patterns",
            self._scan_reasoning_patterns,
            logs,
            bid_queue,
        )
        self._run_pass("training_candidates", self._score_training_candidates)
        self._run_pass("god_nodes", self._scan_god_nodes)

    def _scan_acceptance_rates(
        self,
        logs: list[dict[str, Any]],
        bid_queue: BidQueue,
    ) -> None:
        by_coordinator: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for entry in logs:
            if entry.get("accepted") is None:
                continue
            coordinator_name = str(entry.get("coordinator_name") or "").strip()
            if not coordinator_name:
                continue
            by_coordinator[coordinator_name].append(entry)

        for coordinator_name, entries in by_coordinator.items():
            recent = sorted(
                entries,
                key=lambda entry: float(entry.get("timestamp") or 0.0),
            )[-self.acceptance_window :]
            if len(recent) < self.acceptance_window:
                continue
            accepted_count = sum(1 for entry in recent if entry.get("accepted") is True)
            acceptance_rate = accepted_count / len(recent)
            if acceptance_rate >= ACCEPTANCE_DROP_THRESHOLD:
                continue
            percent = round(acceptance_rate * 100)
            bid_queue.submit(
                Bid(
                    coordinator_name=self.name,
                    content=(
                        f"Pattern: {coordinator_name} bid acceptance has dropped "
                        f"to {percent}% — possible miscalibration"
                    ),
                    priority=PRIORITY_PATTERN,
                    timestamp=self.time_fn(),
                )
            )

    def _scan_reasoning_patterns(
        self,
        logs: list[dict[str, Any]],
        bid_queue: BidQueue,
    ) -> None:
        traces = [
            str(entry.get("reasoning_trace")).strip()
            for entry in logs
            if entry.get("reasoning_trace")
        ]
        if len(traces) < REASONING_REPEAT_THRESHOLD:
            return

        phrases = Counter()
        for trace in traces:
            phrases.update(_reasoning_phrases(trace))

        if not any(
            count >= REASONING_REPEAT_THRESHOLD for count in phrases.values()
        ):
            return

        bid_queue.submit(
            Bid(
                coordinator_name=self.name,
                content=(
                    "Pattern: recurring reasoning trace detected across "
                    f"{len(traces)} entries — possible promotable regularity"
                ),
                priority=PRIORITY_PATTERN,
                timestamp=self.time_fn(),
            )
        )

    def _score_training_candidates(self) -> None:
        entries = self.training_candidate_reader()
        for entry in entries[:TRAINING_CANDIDATE_LIMIT]:
            element_id = str(entry.get("element_id") or entry.get("id") or "").strip()
            if not element_id:
                continue
            score = _training_candidate_score(entry)
            self.training_candidate_writer(element_id, score)

    def _scan_god_nodes(self) -> None:
        nodes = self.god_node_reader(
            self.god_node_degree_threshold,
            GOD_NODE_LOG_LIMIT,
        )
        # TODO: surface god nodes as training domain signals once threshold is calibrated.
        self._write_pattern_log(
            {
                "timestamp": self.time_fn(),
                "type": "god_node_scan",
                "degree_threshold": self.god_node_degree_threshold,
                "nodes": nodes[:GOD_NODE_LOG_LIMIT],
            }
        )

    def _run_pass(self, pass_name: str, func: Callable, *args) -> None:
        try:
            func(*args)
        except Exception as exc:
            self._log_error(pass_name, exc)

    def _log_error(self, pass_name: str, exc: Exception) -> None:
        self._write_pattern_log(
            {
                "timestamp": self.time_fn(),
                "type": "error",
                "pass": pass_name,
                "error": str(exc),
            }
        )

    def _write_pattern_log(self, entry: dict[str, Any]) -> None:
        try:
            self.pattern_log_writer(entry)
        except Exception:
            return


def _reasoning_phrases(trace: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", trace.lower()).strip()
    if not normalized:
        return []

    phrases = [normalized]
    words = re.findall(r"[a-z0-9']+", normalized)
    max_size = min(6, len(words))
    for size in range(3, max_size + 1):
        for index in range(0, len(words) - size + 1):
            phrases.append(" ".join(words[index : index + size]))
    return phrases


def _training_candidate_score(entry: dict[str, Any]) -> float:
    score = 0.0
    confidence = _optional_float(entry.get("confidence"))
    if confidence is not None and confidence >= 0.7:
        score += 0.3
    if entry.get("accepted") is True:
        score += 0.4
    outcome_quality = _optional_float(entry.get("outcome_quality"))
    if outcome_quality is not None and outcome_quality >= 0.6:
        score += 0.3
    return round(score, 4)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _append_pattern_log_entry(
    entry: dict[str, Any],
    path: Path = PATTERN_MONITOR_LOG_PATH,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.open("a", encoding="utf-8").write(
        json.dumps(entry, sort_keys=True, default=str) + "\n"
    )


def _default_training_candidate_reader() -> list[dict[str, Any]]:
    from world_models import config, graph

    driver = graph.connect()
    try:
        with driver.session(database=config.NEO4J_DATABASE) as session:
            records = session.run(
                """
                MATCH (node)
                WHERE (node:Episode OR node:Observation)
                  AND node.training_candidate IS NULL
                RETURN elementId(node) AS element_id,
                       labels(node) AS labels,
                       properties(node) AS properties
                ORDER BY node.created_at DESC
                LIMIT $limit
                """,
                limit=TRAINING_CANDIDATE_LIMIT,
            )
            entries = []
            for record in records:
                entry = dict(record["properties"])
                entry["element_id"] = record["element_id"]
                entry["labels"] = list(record["labels"])
                entries.append(entry)
            return entries
    finally:
        graph.close(driver)


def _default_training_candidate_writer(element_id: str, score: float) -> None:
    from world_models import config, graph

    driver = graph.connect()
    try:
        with driver.session(database=config.NEO4J_DATABASE) as session:
            session.run(
                """
                MATCH (node)
                WHERE elementId(node) = $element_id
                SET node.training_candidate = $score
                """,
                element_id=element_id,
                score=float(score),
            ).consume()
    finally:
        graph.close(driver)


def _default_god_node_reader(threshold: int, limit: int) -> list[dict[str, Any]]:
    from world_models import config, graph

    driver = graph.connect()
    try:
        with driver.session(database=config.NEO4J_DATABASE) as session:
            records = session.run(
                """
                MATCH (node)
                OPTIONAL MATCH (node)--(neighbor)
                WITH node, count(neighbor) AS degree
                WHERE degree > $threshold
                RETURN elementId(node) AS element_id,
                       labels(node) AS labels,
                       properties(node) AS properties,
                       degree
                ORDER BY degree DESC
                LIMIT $limit
                """,
                threshold=int(threshold),
                limit=int(limit),
            )
            nodes = []
            for record in records:
                props = dict(record["properties"])
                nodes.append(
                    {
                        "element_id": record["element_id"],
                        "labels": list(record["labels"]),
                        "degree": int(record["degree"]),
                        "name": props.get("name"),
                        "content": props.get("content"),
                        "environment": props.get("environment"),
                    }
                )
            return nodes
    finally:
        graph.close(driver)
