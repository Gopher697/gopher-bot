from __future__ import annotations

import asyncio

from coordinators.archivist import (
    ARCHIVIST_BATCH_SIZE,
    Archivist,
    _build_research_entry,
    _extract_claims,
    _filter_unprocessed,
    _is_noteworthy,
)
import coordinators.archivist as archivist_module


class _RecordingQueue:
    def __init__(self) -> None:
        self.submitted = []

    def submit(self, bid) -> None:
        self.submitted.append(bid)


def _turn(turn_id: str, **overrides) -> dict:
    base = {
        "turn_id": turn_id,
        "session_id": "session1",
        "orientation_active_goal": "",
        "prediction_accuracy_ema": 0.5,
        "has_error": False,
    }
    base.update(overrides)
    return base


def _graph_writer(*_args) -> tuple[str, str]:
    return "source123", "learning123"


def _claim_writer(*_args) -> list[str]:
    return []


def test_noteworthy_on_error():
    assert _is_noteworthy({"has_error": True}) is True


def test_noteworthy_on_active_goal():
    assert _is_noteworthy({"orientation_active_goal": "write keeper"}) is True


def test_noteworthy_on_low_ema():
    assert _is_noteworthy({"prediction_accuracy_ema": 0.1}) is True


def test_not_noteworthy_empty_turn():
    assert _is_noteworthy({}) is False


def test_not_noteworthy_short_goal():
    assert _is_noteworthy({"orientation_active_goal": "ok"}) is False


def test_filter_no_last_id():
    turns = [_turn(f"t{i}") for i in range(3)]
    assert _filter_unprocessed(turns, "") == turns


def test_filter_skips_processed():
    turns = [_turn(f"t{i}") for i in range(5)]
    assert _filter_unprocessed(turns, "t2") == turns[3:]


def test_filter_id_not_found():
    turns = [_turn(f"t{i}") for i in range(3)]
    assert _filter_unprocessed(turns, "missing") == turns


def test_filter_empty_list():
    assert _filter_unprocessed([], "t1") == []


def test_build_entry_has_required_keys():
    entry = _build_research_entry(_turn("t1"), _graph_writer, _claim_writer)
    for key in (
        "research_id",
        "turn_id",
        "session_id",
        "trigger",
        "active_goal",
        "status",
    ):
        assert key in entry


def test_build_entry_trigger_error():
    entry = _build_research_entry(_turn("t1", has_error=True), _graph_writer, _claim_writer)
    assert "error" in entry["trigger"]


def test_build_entry_trigger_goal():
    entry = _build_research_entry(
        _turn("t1", orientation_active_goal="write keeper"),
        _graph_writer,
        _claim_writer,
    )
    assert "goal_progress" in entry["trigger"]


def test_build_entry_trigger_low_ema():
    entry = _build_research_entry(
        _turn("t1", prediction_accuracy_ema=0.1),
        _graph_writer,
        _claim_writer,
    )
    assert "low_accuracy" in entry["trigger"]


def test_build_entry_status_filed():
    entry = _build_research_entry(_turn("t1"), _graph_writer, _claim_writer)
    assert entry["status"] == "filed"


def test_extract_claims_returns_empty_on_empty_input():
    assert _extract_claims("", "") == []


def test_build_research_entry_calls_claim_writer(monkeypatch):
    extracted_claims = [{"text": "A claim.", "confidence": 0.8}]
    calls = []

    def graph_writer(*_args) -> tuple[str, str]:
        return "src-1", "le-1"

    def claim_writer(source_id, learning_id, claims, environment) -> list[str]:
        calls.append((source_id, learning_id, claims, environment))
        return ["cid-1"]

    monkeypatch.setattr(
        archivist_module,
        "_extract_claims",
        lambda _message, _response: extracted_claims,
    )

    entry = _build_research_entry(
        _turn("t1", message="test", response="response"),
        graph_writer,
        claim_writer,
    )

    assert calls == [("src-1", "le-1", extracted_claims, "global")]
    assert entry["claim_count"] == 1
    assert entry["claim_ids"] == ["cid-1"]


def test_build_research_entry_skips_claims_on_empty_text(monkeypatch):
    calls = []

    monkeypatch.setattr(
        archivist_module,
        "_extract_claims",
        lambda _message, _response: [{"text": "A claim.", "confidence": 0.8}],
    )

    entry = _build_research_entry(
        _turn("t1"),
        _graph_writer,
        lambda *args: calls.append(args) or ["cid-1"],
    )

    assert calls == []
    assert entry["claim_count"] == 0
    assert entry["claim_ids"] == []


def test_archivist_accepts_claim_writer_override():
    Archivist(claim_writer=lambda *_args, **_kwargs: [])


def test_background_tick_no_noteworthy_no_bid():
    written = []
    queue = _RecordingQueue()
    archivist = Archivist(
        turn_log_reader=lambda _limit: [],
        research_log_writer=written.append,
        graph_writer=_graph_writer,
    )

    asyncio.run(archivist.background_tick(queue))

    assert written == []
    assert queue.submitted == []


def test_background_tick_archives_noteworthy_turns():
    written = []
    queue = _RecordingQueue()
    turns = [
        _turn("t1", orientation_active_goal="write keeper"),
        _turn("t2", has_error=True),
    ]
    archivist = Archivist(
        turn_log_reader=lambda _limit: turns,
        research_log_writer=written.append,
        graph_writer=_graph_writer,
    )

    asyncio.run(archivist.background_tick(queue))

    assert len(written) == 2
    assert len(queue.submitted) == 1
    assert "2 research entries" in queue.submitted[0].content


def test_background_tick_updates_last_processed_turn_id():
    written = []
    turns = [
        _turn("t1", orientation_active_goal="write keeper"),
        _turn("t2", has_error=True),
    ]
    archivist = Archivist(
        turn_log_reader=lambda _limit: turns,
        research_log_writer=written.append,
        graph_writer=_graph_writer,
    )

    asyncio.run(archivist.background_tick(_RecordingQueue()))

    assert archivist.state.last_processed_turn_id == "t2"


def test_background_tick_respects_batch_size():
    written = []
    turns = [
        _turn(f"t{i}", orientation_active_goal=f"goal {i}")
        for i in range(20)
    ]
    archivist = Archivist(
        turn_log_reader=lambda _limit: turns,
        research_log_writer=written.append,
        graph_writer=_graph_writer,
    )

    asyncio.run(archivist.background_tick(_RecordingQueue()))

    assert len(written) == ARCHIVIST_BATCH_SIZE


def test_process_adds_research_count():
    archivist = Archivist(turn_log_reader=lambda _limit: [])
    packet = archivist.process({})
    assert packet["archivist_research_count"] == 0


def test_brain_loop_registers_archivist_at_cadence():
    from coordinators.archivist import ARCHIVIST_CADENCE_SECONDS
    from coordinators.brain_loop import BACKGROUND_COORDINATORS, BACKGROUND_INTERVALS

    assert "archivist" in BACKGROUND_COORDINATORS
    assert BACKGROUND_INTERVALS["archivist"] == ARCHIVIST_CADENCE_SECONDS


def test_default_background_coordinators_uses_real_archivist():
    from coordinators.brain_loop import _default_background_coordinators

    coordinators = _default_background_coordinators()
    assert isinstance(coordinators["archivist"], Archivist)
