from __future__ import annotations

import json
import tempfile
from pathlib import Path

from tests.conftest import isolated_awareness


# ---------------------------------------------------------------------------
# Policy engine tests
# ---------------------------------------------------------------------------

def test_classify_read_file_is_whitelist():
    from coordinators.hands_policy import classify_action

    decision = classify_action("read_file", {"path": "/tmp/notes.txt"})
    assert decision.policy_class == "whitelist"


def test_classify_write_file_is_greylist():
    from coordinators.hands_policy import classify_action

    decision = classify_action("write_file", {"path": "/tmp/output.txt"})
    assert decision.policy_class == "greylist"


def test_classify_delete_file_is_blacklist():
    from coordinators.hands_policy import classify_action

    decision = classify_action("delete_file", {"path": "/tmp/output.txt"})
    assert decision.policy_class == "blacklist"


def test_classify_config_path_is_blacklisted_regardless_of_action():
    from coordinators.hands_policy import classify_action

    for action_type in ("read_file", "write_file", "append_note"):
        decision = classify_action(
            action_type, {"path": "world_models/config.py"}
        )
        assert decision.policy_class == "blacklist", (
            f"Expected blacklist for {action_type!r} on config.py, "
            f"got {decision.policy_class!r}"
        )


def test_classify_env_path_is_blacklisted():
    from coordinators.hands_policy import classify_action

    decision = classify_action("read_file", {"path": "/home/user/.env"})
    assert decision.policy_class == "blacklist"


def test_classify_unknown_action_defaults_to_greylist():
    from coordinators.hands_policy import classify_action

    decision = classify_action("unknown_future_action", {})
    assert decision.policy_class == "greylist"


# ---------------------------------------------------------------------------
# Hands.process — policy interception
# ---------------------------------------------------------------------------

def test_hands_blocks_blacklist_action():
    from coordinators.hands import Hands

    log = []
    hands = Hands(action_log_writer=log.append)
    packet = {"action": {"type": "delete_file", "args": {"path": "/tmp/x.txt"}}}

    result = hands.process(packet)

    assert result["action_result"]["status"] == "blocked"
    assert result["action_result"]["policy_class"] == "blacklist"
    assert len(log) == 1
    assert log[0]["status"] == "blocked"


def test_hands_queues_greylist_action_without_executing():
    from coordinators.hands import Hands

    log = []
    executed = []

    def fake_write(args):
        executed.append(args)

    hands = Hands(action_log_writer=log.append)
    packet = {
        "action": {
            "type": "write_file",
            "args": {"path": "/tmp/out.txt", "content": "hello"},
        }
    }

    result = hands.process(packet)

    assert result["action_result"]["status"] == "pending_approval"
    assert result["action_result"]["policy_class"] == "greylist"
    assert len(executed) == 0, "greylist action must not execute without approval"
    assert len(log) == 1


def test_hands_executes_whitelist_read_file():
    from coordinators.hands import Hands

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as fh:
        fh.write("hello gopher")
        tmp_path = fh.name

    log = []
    hands = Hands(action_log_writer=log.append)
    packet = {"action": {"type": "read_file", "args": {"path": tmp_path}}}

    result = hands.process(packet)

    assert result["action_result"]["status"] == "executed"
    assert result["action_result"]["output"] == "hello gopher"
    assert len(log) == 1
    assert log[0]["status"] == "executed"


def test_hands_executes_whitelist_list_directory():
    from coordinators.hands import Hands

    with tempfile.TemporaryDirectory() as tmpdir:
        Path(tmpdir, "alpha.txt").write_text("a")
        Path(tmpdir, "beta.txt").write_text("b")

        log = []
        hands = Hands(action_log_writer=log.append)
        packet = {"action": {"type": "list_directory", "args": {"path": tmpdir}}}

        result = hands.process(packet)

    assert result["action_result"]["status"] == "executed"
    assert set(result["action_result"]["output"]) == {"alpha.txt", "beta.txt"}


def test_hands_returns_packet_unchanged_when_no_action_key():
    from coordinators.hands import Hands

    hands = Hands(action_log_writer=lambda e: None)
    packet = {"message": "hello", "reason_output": "some output"}

    result = hands.process(packet)

    assert result is packet
    assert "action_result" not in result


def test_hands_config_path_is_blocked_even_for_read():
    from coordinators.hands import Hands

    log = []
    hands = Hands(action_log_writer=log.append)
    packet = {
        "action": {
            "type": "read_file",
            "args": {"path": "D:/Gopher Bot/gopher-bot/world_models/config.py"},
        }
    }

    result = hands.process(packet)

    assert result["action_result"]["status"] == "blocked"
    assert result["action_result"]["policy_class"] == "blacklist"


# ---------------------------------------------------------------------------
# Snapshot / rollback
# ---------------------------------------------------------------------------

def test_hands_rolls_back_on_append_error():
    from coordinators.hands import Hands, _WHITELIST_HANDLERS

    original_content = b"original content"
    snapshots = []
    restored = []

    def fake_snapshot(path):
        snapshots.append(path)
        return original_content

    def fake_restore(path, data):
        restored.append((path, data))

    def failing_append(args):
        raise OSError("disk full")

    log = []
    hands = Hands(
        action_log_writer=log.append,
        snapshot_fn=fake_snapshot,
        restore_fn=fake_restore,
    )
    # Temporarily replace handler to force an error
    original_handler = _WHITELIST_HANDLERS.get("append_note")
    _WHITELIST_HANDLERS["append_note"] = failing_append

    try:
        packet = {
            "action": {
                "type": "append_note",
                "args": {"path": "/tmp/notes.txt", "content": "new entry"},
            }
        }
        result = hands.process(packet)
    finally:
        if original_handler is not None:
            _WHITELIST_HANDLERS["append_note"] = original_handler
        else:
            del _WHITELIST_HANDLERS["append_note"]

    assert result["action_result"]["status"] == "error"
    assert len(snapshots) == 1
    assert len(restored) == 1
    assert restored[0][1] == original_content


# ---------------------------------------------------------------------------
# Action logging
# ---------------------------------------------------------------------------

def test_hands_action_log_contains_required_fields():
    from coordinators.hands import Hands

    log = []
    hands = Hands(action_log_writer=log.append, time_fn=lambda: 9999.0)
    packet = {"action": {"type": "delete_file", "args": {"path": "/tmp/x"}}}

    hands.process(packet)

    assert len(log) == 1
    entry = log[0]
    assert entry["timestamp"] == 9999.0
    assert entry["action_type"] == "delete_file"
    assert entry["policy_class"] == "blacklist"
    assert entry["status"] == "blocked"
    assert "reason" in entry


def test_hands_action_log_truncates_long_args():
    from coordinators.hands import Hands

    log = []
    hands = Hands(action_log_writer=log.append)
    long_content = "x" * 500
    packet = {
        "action": {
            "type": "write_file",
            "args": {"path": "/tmp/out.txt", "content": long_content},
        }
    }

    hands.process(packet)

    assert len(log) == 1
    logged_content = log[0]["args_summary"]["content"]
    assert len(logged_content) <= 204  # 200 chars + "…"


# ---------------------------------------------------------------------------
# Awareness pipeline integration
# ---------------------------------------------------------------------------

def test_awareness_calls_hands_when_action_in_packet():
    from coordinators.awareness import Awareness
    from coordinators.base import Coordinator
    from coordinators.hands import Hands

    class FakeSensory(Coordinator):
        name = "sensory"
        def process(self, packet):
            return packet

    class FakeMemory(Coordinator):
        name = "memory"
        def process(self, packet):
            return packet

    class FakeReason(Coordinator):
        name = "reason"
        def process(self, packet):
            packet["reason_output"] = "Reading the file now."
            packet["action"] = {
                "type": "list_directory",
                "args": {"path": "/tmp"},
            }
            return packet

    class FakeVoice(Coordinator):
        name = "voice"
        def process(self, packet):
            packet["final_response"] = packet.get("reason_output", "")
            return packet

    log = []
    hands = Hands(action_log_writer=log.append)
    awareness = isolated_awareness(
        sensory=FakeSensory(),
        memory=FakeMemory(),
        reason=FakeReason(),
        voice=FakeVoice(),
        hands=hands,
    )

    result = awareness.synchronous_run("list files")

    assert "action_result" in result
    assert result["action_result"]["status"] == "executed"
    assert len(log) == 1


def test_awareness_skips_hands_when_no_action_in_packet():
    from coordinators.awareness import Awareness
    from coordinators.base import Coordinator
    from coordinators.hands import Hands

    class FakeSensory(Coordinator):
        name = "sensory"
        def process(self, packet):
            return packet

    class FakeMemory(Coordinator):
        name = "memory"
        def process(self, packet):
            return packet

    class FakeReason(Coordinator):
        name = "reason"
        def process(self, packet):
            packet["reason_output"] = "Just a normal response."
            # No action key
            return packet

    class FakeVoice(Coordinator):
        name = "voice"
        def process(self, packet):
            packet["final_response"] = packet.get("reason_output", "")
            return packet

    log = []
    hands = Hands(action_log_writer=log.append)
    awareness = isolated_awareness(
        sensory=FakeSensory(),
        memory=FakeMemory(),
        reason=FakeReason(),
        voice=FakeVoice(),
        hands=hands,
    )

    result = awareness.synchronous_run("just chat")

    assert "action_result" not in result
    assert len(log) == 0


# ---------------------------------------------------------------------------
# bid.py priority ordering
# ---------------------------------------------------------------------------

def test_hands_priority_is_higher_than_pattern():
    from coordinators.bid import PRIORITY_HANDS, PRIORITY_PATTERN

    assert PRIORITY_HANDS < PRIORITY_PATTERN, (
        "PRIORITY_HANDS should be numerically lower (higher urgency) than PRIORITY_PATTERN"
    )
