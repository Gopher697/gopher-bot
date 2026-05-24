from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from coordinators.base import Coordinator


ARCHIVIST_CADENCE_SECONDS = 300
ARCHIVIST_PRIORITY = 5
ARCHIVIST_BATCH_SIZE = 10
ARCHIVIST_LOW_EMA_THRESHOLD = 0.30
ARCHIVIST_MIN_GOAL_LENGTH = 5

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARCHIVIST_RESEARCH_LOG_PATH = (
    _PROJECT_ROOT / "logs" / "archivist" / "research.jsonl"
)


@dataclass
class ArchivistState:
    last_processed_turn_id: str = ""
    research_count: int = 0
    last_tick: datetime | None = None
    last_bid_content: str | None = None


@dataclass(frozen=True)
class ArchivistBid:
    coordinator_name: str
    content: str
    priority: int
    timestamp: float
    source: str = "archivist"
    type: str = "research_signal"


def _default_turn_log_reader(limit: int) -> list[dict]:
    from coordinators.base import read_turn_log_entries

    return read_turn_log_entries(limit=limit)


def _default_research_log_writer(entry: dict) -> None:
    import json

    path = ARCHIVIST_RESEARCH_LOG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def _extract_claims(message: str, response: str) -> list[dict]:
    """
    Call the local LLM (qwen2.5-3b-instruct via LM Studio) to extract
    1-3 durable factual claims from a conversation turn.

    Returns a list of dicts: [{"text": str, "confidence": float}, ...]
    Returns [] on any failure - extraction is always optional.
    """
    import json

    text = f"User: {message}\nAssistant: {response}".strip()
    if not text or text == "User: \nAssistant:":
        return []

    prompt = (
        "Extract 1 to 3 factual, durable claims from this conversation turn.\n"
        "A claim is a short declarative statement about what is true or was observed.\n"
        "Return a JSON array of objects with keys: \"text\" (string) and "
        "\"confidence\" (float 0.0-1.0).\n"
        "Return ONLY the JSON array. No explanation.\n\n"
        f"{text}"
    )

    try:
        from openai import OpenAI

        client = OpenAI(
            base_url="http://localhost:1234/v1",
            api_key="lm-studio",
        )
        completion = client.chat.completions.create(
            model="qwen2.5-3b-instruct",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=256,
            temperature=0.2,
        )
        raw = (completion.choices[0].message.content or "").strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            return []
        result = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            text_val = str(item.get("text") or "").strip()
            if not text_val:
                continue
            conf = float(item.get("confidence") or 0.5)
            conf = max(0.0, min(1.0, conf))
            result.append({"text": text_val, "confidence": conf})
        return result[:3]
    except Exception:
        return []


def _default_graph_writer(
    session_id: str,
    environment: str,
    coordinator: str,
    active_goal: str,
    turn_id: str | None,
) -> tuple[str, str]:
    driver = None
    try:
        from world_models import graph

        driver = graph.connect()
        source_id = graph.create_source(
            driver=driver,
            title=active_goal or "Autonomous observation",
            source_type="internal",
            environment=environment,
            summary=f"Self-generated research note from turn {turn_id or 'unknown'}",
        )
        learning_id = graph.create_learning_episode(
            driver=driver,
            session_id=session_id,
            environment=environment,
            coordinator=coordinator,
            learning_type="autonomous",
            source_id=source_id,
            turn_id=turn_id,
            summary=active_goal or "Autonomous learning event",
        )
        graph.link_learning_episode_to_source(
            driver,
            learning_id,
            source_id,
            environment,
        )
        return source_id, learning_id
    except Exception:
        return "", ""
    finally:
        if driver is not None:
            try:
                graph.close(driver)
            except Exception:
                pass


def _default_claim_writer(
    source_id: str,
    learning_id: str,
    claims: list[dict],
    environment: str,
) -> list[str]:
    """
    Write extracted claims to the graph and link them to the given
    Source and LearningEpisode. Returns list of created claim_ids.
    """
    if not claims or not source_id:
        return []

    driver = None
    try:
        from world_models import graph

        driver = graph.connect()
        claim_ids: list[str] = []
        for claim in claims:
            claim_id = graph.create_claim(
                driver=driver,
                content=claim["text"],
                source_id=source_id,
                environment=environment,
                coordinator="archivist",
                confidence=claim.get("confidence", 0.5),
                status="candidate",
            )
            graph.link_source_to_claim(driver, source_id, claim_id, environment)
            if learning_id:
                graph.link_learning_episode_to_claim(
                    driver, learning_id, claim_id, environment
                )
            claim_ids.append(claim_id)
        return claim_ids
    except Exception:
        return []
    finally:
        if driver is not None:
            try:
                graph.close(driver)
            except Exception:
                pass


def _filter_unprocessed(
    turns: list[dict],
    last_processed_turn_id: str,
) -> list[dict]:
    if not last_processed_turn_id:
        return list(turns)
    for index, turn in enumerate(turns):
        if str(turn.get("turn_id") or "") == last_processed_turn_id:
            return turns[index + 1:]
    return list(turns)


def _is_noteworthy(turn: dict) -> bool:
    if turn.get("has_error"):
        return True

    active_goal = str(turn.get("orientation_active_goal") or "")
    if len(active_goal) >= ARCHIVIST_MIN_GOAL_LENGTH:
        return True

    ema = float(turn.get("prediction_accuracy_ema") or 0.5)
    return ema < ARCHIVIST_LOW_EMA_THRESHOLD


def _build_research_entry(
    turn: dict,
    graph_writer: Callable,
    claim_writer: Callable,
) -> dict:
    import uuid

    turn_id = str(turn.get("turn_id") or "")
    session_id = str(turn.get("session_id") or "")
    active_goal = str(turn.get("orientation_active_goal") or "")
    ema = float(turn.get("prediction_accuracy_ema") or 0.5)
    has_error = bool(turn.get("has_error"))

    triggers: list[str] = []
    if has_error:
        triggers.append("error")
    if len(active_goal) >= ARCHIVIST_MIN_GOAL_LENGTH:
        triggers.append("goal_progress")
    if ema < ARCHIVIST_LOW_EMA_THRESHOLD:
        triggers.append("low_accuracy")

    source_id, learning_id = graph_writer(
        session_id,
        "global",
        "archivist",
        active_goal,
        turn_id or None,
    )

    # Claim extraction - optional, fails silently.
    message = str(turn.get("message") or "")
    response = str(turn.get("response") or "")
    claims: list[dict] = []
    claim_ids: list[str] = []
    if message or response:
        claims = _extract_claims(message, response)
        if claims and source_id:
            claim_ids = claim_writer(source_id, learning_id, claims, "global")

    return {
        "research_id": uuid.uuid4().hex,
        "timestamp": datetime.now(UTC).isoformat(),
        "turn_id": turn_id,
        "session_id": session_id,
        "trigger": ",".join(triggers) or "unknown",
        "active_goal": active_goal,
        "prediction_accuracy_ema": round(ema, 4),
        "has_error": has_error,
        "source_id": source_id,
        "learning_id": learning_id,
        "claim_count": len(claim_ids),
        "claim_ids": claim_ids,
        "status": "filed",
    }


class Archivist(Coordinator):
    name = "archivist"

    def __init__(
        self,
        turn_log_reader: Callable[[int], list[dict]] | None = None,
        research_log_writer: Callable[[dict], None] | None = None,
        graph_writer: Callable[
            [str, str, str, str, str | None],
            tuple[str, str],
        ] | None = None,
        claim_writer: Callable[
            [str, str, list[dict], str],
            list[str],
        ] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.turn_log_reader = turn_log_reader or _default_turn_log_reader
        self.research_log_writer = research_log_writer or _default_research_log_writer
        self.graph_writer = graph_writer or _default_graph_writer
        self.claim_writer = claim_writer or _default_claim_writer
        self.clock = clock or (lambda: datetime.now(UTC))
        self.state = ArchivistState()

    def process(self, packet: dict) -> dict:
        packet["archivist_research_count"] = self.state.research_count
        return packet

    async def background_tick(self, awareness_queue) -> None:
        self.state.last_tick = self.clock()
        turns = self.turn_log_reader(ARCHIVIST_BATCH_SIZE * 3)

        new_turns = _filter_unprocessed(turns, self.state.last_processed_turn_id)
        noteworthy = [
            turn for turn in new_turns
            if _is_noteworthy(turn)
        ][:ARCHIVIST_BATCH_SIZE]

        if not noteworthy:
            return

        archived_count = 0
        last_turn_id = self.state.last_processed_turn_id

        for turn in noteworthy:
            entry = _build_research_entry(turn, self.graph_writer, self.claim_writer)
            try:
                self.research_log_writer(entry)
            except Exception:
                continue

            archived_count += 1
            self.state.research_count += 1
            turn_id = str(turn.get("turn_id") or "")
            if turn_id:
                last_turn_id = turn_id

        if last_turn_id:
            self.state.last_processed_turn_id = last_turn_id

        if archived_count <= 0:
            return

        observation = (
            f"Archivist: filed {archived_count} research "
            f"entr{'y' if archived_count == 1 else 'ies'} from turn log. "
            f"Total this session: {self.state.research_count}."
        )
        if observation == self.state.last_bid_content:
            return

        import time as _time

        bid = ArchivistBid(
            coordinator_name=self.name,
            content=observation,
            priority=ARCHIVIST_PRIORITY,
            timestamp=_time.time(),
        )
        awareness_queue.submit(bid)
        self.state.last_bid_content = observation
