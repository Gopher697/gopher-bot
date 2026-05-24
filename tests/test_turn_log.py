from __future__ import annotations

import json


def test_build_turn_log_entry_minimal():
    from coordinators.base import build_turn_log_entry

    entry = build_turn_log_entry({"session_id": "sess1", "turn_id": "turn1"})

    assert entry["session_id"] == "sess1"
    assert entry["turn_id"] == "turn1"
    assert entry["predicted_topic"] == ""
    assert entry["last_prediction_accuracy"] == 0.0
    assert entry["prediction_accuracy_ema"] == 0.5
    assert entry["low_accuracy_streak"] == 0
    assert entry["has_error"] is False


def test_build_turn_log_entry_full_mirror_self_state():
    from coordinators.base import build_turn_log_entry

    entry = build_turn_log_entry({
        "mirror_self_state": {
            "predicted_topic": "goal substrate",
            "last_prediction_accuracy": 0.4,
            "prediction_accuracy_ema": 0.6,
            "low_accuracy_streak": 2,
            "self_affect": "engaged",
        },
    })

    assert entry["predicted_topic"] == "goal substrate"
    assert entry["last_prediction_accuracy"] == 0.4
    assert entry["prediction_accuracy_ema"] == 0.6
    assert entry["low_accuracy_streak"] == 2
    assert entry["self_affect"] == "engaged"


def test_build_turn_log_entry_trust_level():
    from coordinators.base import build_turn_log_entry

    assert build_turn_log_entry({"trust_level": 1})["trust_level"] == 1


def test_build_turn_log_entry_has_error_true():
    from coordinators.base import build_turn_log_entry

    assert build_turn_log_entry({"error": "something failed"})["has_error"] is True


def test_build_turn_log_entry_has_error_false():
    from coordinators.base import build_turn_log_entry

    assert build_turn_log_entry({})["has_error"] is False


def test_build_turn_log_entry_bid_count():
    from coordinators.base import build_turn_log_entry

    entry = build_turn_log_entry({"background_bids": [{}, {}, {}]})

    assert entry["bid_count"] == 3


def test_build_turn_log_entry_orientation_goal():
    from coordinators.base import build_turn_log_entry

    entry = build_turn_log_entry({
        "orientation": {"active_goal_focus": "write keeper"},
    })

    assert entry["orientation_active_goal"] == "write keeper"


def test_build_turn_log_entry_safe_on_empty_packet():
    from coordinators.base import build_turn_log_entry

    entry = build_turn_log_entry({})

    assert entry["turn_id"] == ""
    assert entry["session_id"] == ""
    assert entry["trust_level"] == 0
    assert entry["actual_cost_usd"] == 0.0


def test_append_turn_log_creates_file(tmp_path):
    from coordinators.base import append_turn_log_entry

    log_path = tmp_path / "audit" / "turns.jsonl"
    append_turn_log_entry({"turn_id": "t1"}, path=log_path)

    assert log_path.exists()
    assert len(log_path.read_text(encoding="utf-8").splitlines()) == 1


def test_read_turn_log_empty_file_returns_empty_list(tmp_path):
    from coordinators.base import read_turn_log_entries

    assert read_turn_log_entries(path=tmp_path / "missing.jsonl") == []


def test_read_turn_log_round_trip(tmp_path):
    from coordinators.base import append_turn_log_entry, read_turn_log_entries

    log_path = tmp_path / "turns.jsonl"
    for idx in range(3):
        append_turn_log_entry({"turn_id": f"t{idx}"}, path=log_path)

    entries = read_turn_log_entries(path=log_path)

    assert [entry["turn_id"] for entry in entries] == ["t0", "t1", "t2"]


def test_read_turn_log_respects_limit(tmp_path):
    from coordinators.base import append_turn_log_entry, read_turn_log_entries

    log_path = tmp_path / "turns.jsonl"
    for idx in range(10):
        append_turn_log_entry({"turn_id": f"t{idx}"}, path=log_path)

    entries = read_turn_log_entries(limit=3, path=log_path)

    assert [entry["turn_id"] for entry in entries] == ["t7", "t8", "t9"]


def test_read_turn_log_skips_blank_and_malformed_lines(tmp_path):
    from coordinators.base import read_turn_log_entries

    log_path = tmp_path / "turns.jsonl"
    log_path.write_text(
        json.dumps({"turn_id": "valid"}) + "\n\nnot json\n",
        encoding="utf-8",
    )

    entries = read_turn_log_entries(path=log_path)

    assert entries == [{"turn_id": "valid"}]


def test_awareness_writes_turn_log_after_voice(monkeypatch):
    from coordinators.awareness import Awareness
    from coordinators.base import Coordinator

    class Noop(Coordinator):
        name = "noop"

        def process(self, packet):
            return packet

    written = []
    monkeypatch.setattr(
        "coordinators.awareness.append_turn_log_entry",
        lambda entry: written.append(entry),
    )

    awareness = Awareness(
        sensory=Noop(),
        memory=Noop(),
        orientation=Noop(),
        keeper=Noop(),
        mirror_user=Noop(),
        mirror_self=Noop(),
        ethos=Noop(),
        drive=Noop(),
        reason=Noop(),
        voice=Noop(),
    )

    packet = awareness.run("hello")

    assert packet["turn_id"]
    assert len(written) == 1
    assert written[0]["turn_id"] == packet["turn_id"]
