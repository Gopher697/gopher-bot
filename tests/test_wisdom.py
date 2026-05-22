from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from coordinators.bid import BidQueue
from coordinators.wisdom import (
    WISDOM_RECURRENCE_THRESHOLD,
    Wisdom,
    WisdomState,
    _append_wisdom_observation_log_entry,
)
from tests.helpers import make_workspace


NOW = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)


def _turn(accuracy: float = 0.5, goal: str = "", has_error: bool = False) -> dict:
    return {
        "last_prediction_accuracy": accuracy,
        "orientation_active_goal": goal,
        "has_error": has_error,
    }


def _wisdom(
    *,
    turns: list[dict] | None = None,
    research: list[dict] | None = None,
    patterns: list[dict] | None = None,
):
    written = []
    wisdom = Wisdom(
        turn_log_reader=lambda limit: list(turns or []),
        research_log_reader=lambda limit: list(research or []),
        pattern_log_reader=lambda limit: list(patterns or []),
        learning_episode_reader=lambda limit: [],
        wisdom_history_reader=lambda days: [],
        observation_log_writer=written.append,
        clock=lambda: NOW,
        _load_state_fn=WisdomState,
        _save_state_fn=lambda state: None,
    )
    return wisdom, written


def test_wisdom_no_op_foreground():
    wisdom, _written = _wisdom()
    packet = {"message": "hello"}

    result = wisdom.process(packet)

    assert result is packet


def test_accuracy_trend_down():
    wisdom, _written = _wisdom(
        turns=[
            _turn(0.9),
            _turn(0.8),
            _turn(0.4),
            _turn(0.3),
        ]
    )
    queue = BidQueue()

    asyncio.run(wisdom.background_tick(queue))

    bid = queue.get_pending()[0]
    assert "DOWN" in bid.content or "down" in bid.content


def test_accuracy_trend_up():
    wisdom, _written = _wisdom(
        turns=[
            _turn(0.3),
            _turn(0.4),
            _turn(0.8),
            _turn(0.9),
        ]
    )
    queue = BidQueue()

    asyncio.run(wisdom.background_tick(queue))

    bid = queue.get_pending()[0]
    assert "UP" in bid.content or "up" in bid.content


def test_accuracy_stable():
    wisdom, written = _wisdom(
        turns=[
            _turn(0.5),
            _turn(0.5),
            _turn(0.5),
            _turn(0.5),
        ]
    )

    asyncio.run(wisdom.background_tick(BidQueue()))

    assert written[0]["accuracy_trend"] == "stable"


def test_recurring_goal_detected():
    goal = "resolve embedder latency"
    wisdom, written = _wisdom(
        turns=[_turn(0.6, goal=goal) for _ in range(WISDOM_RECURRENCE_THRESHOLD + 1)]
    )

    asyncio.run(wisdom.background_tick(BidQueue()))

    assert goal in written[0]["recurring_goals"]


def test_no_bid_when_nothing_to_report():
    wisdom, _written = _wisdom()
    queue = BidQueue()

    asyncio.run(wisdom.background_tick(queue))

    assert queue.get_pending() == []


def test_bid_submitted_on_signal():
    wisdom, _written = _wisdom(turns=[_turn(0.2, has_error=True)])
    queue = BidQueue()

    asyncio.run(wisdom.background_tick(queue))

    bids = queue.get_pending()
    assert len(bids) == 1
    assert bids[0].source == "wisdom"
    assert bids[0].type == "historical_insight"


def test_observation_log_written():
    tmp_path = make_workspace("wisdom-log")
    log_dir = tmp_path / "logs" / "wisdom"
    wisdom = Wisdom(
        turn_log_reader=lambda limit: [_turn(0.75)],
        research_log_reader=lambda limit: [],
        pattern_log_reader=lambda limit: [],
        learning_episode_reader=lambda limit: [],
        wisdom_history_reader=lambda days: [],
        observation_log_writer=lambda entry: _append_wisdom_observation_log_entry(
            entry,
            log_dir=log_dir,
        ),
        clock=lambda: NOW,
        _load_state_fn=WisdomState,
        _save_state_fn=lambda state: None,
    )

    asyncio.run(wisdom.background_tick(BidQueue()))

    log_path = log_dir / "20260522.jsonl"
    assert log_path.exists()
    entry = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert entry["timestamp"] == NOW.isoformat()
    assert entry["turn_window_size"] == 1
    assert entry["accuracy_mean"] == 0.75
    assert entry["accuracy_trend"] == "stable"
    assert entry["recurring_goals"] == []
    assert entry["pattern_monitor_recurrences"] == []
    assert isinstance(entry["insight"], str)
    assert entry["bid_submitted"] is True


def test_pattern_monitor_recurrence_detected():
    pattern = "low acceptance rate"
    wisdom, written = _wisdom(
        patterns=[{"description": pattern} for _ in range(3)]
    )

    asyncio.run(wisdom.background_tick(BidQueue()))

    assert pattern in written[0]["pattern_monitor_recurrences"]


def test_wisdom_cadence_respected():
    calls = []
    wisdom = Wisdom(
        turn_log_reader=lambda limit: calls.append(("turns", limit)) or [],
        research_log_reader=lambda limit: calls.append(("research", limit)) or [],
        pattern_log_reader=lambda limit: calls.append(("patterns", limit)) or [],
        learning_episode_reader=lambda limit: calls.append(("learning", limit)) or [],
        wisdom_history_reader=lambda days: [],
        observation_log_writer=lambda entry: calls.append(("write", entry)),
        clock=lambda: NOW,
        _load_state_fn=WisdomState,
        _save_state_fn=lambda state: None,
    )
    wisdom.state.last_tick = NOW

    asyncio.run(wisdom.background_tick(BidQueue()))

    assert calls == []


def test_wisdom_state_persists_across_restart():
    saved = {}

    def save_state(state: WisdomState) -> None:
        saved["last_tick"] = state.last_tick

    first = Wisdom(
        turn_log_reader=lambda limit: [_turn(0.75)],
        research_log_reader=lambda limit: [],
        pattern_log_reader=lambda limit: [],
        learning_episode_reader=lambda limit: [],
        wisdom_history_reader=lambda days: [],
        observation_log_writer=lambda entry: None,
        clock=lambda: NOW,
        _load_state_fn=WisdomState,
        _save_state_fn=save_state,
    )

    asyncio.run(first.background_tick(BidQueue()))

    second = Wisdom(
        turn_log_reader=lambda limit: [],
        research_log_reader=lambda limit: [],
        pattern_log_reader=lambda limit: [],
        learning_episode_reader=lambda limit: [],
        wisdom_history_reader=lambda days: [],
        observation_log_writer=lambda entry: None,
        clock=lambda: NOW,
        _load_state_fn=lambda: WisdomState(last_tick=saved["last_tick"]),
        _save_state_fn=lambda state: None,
    )

    assert second.state.last_tick is not None
