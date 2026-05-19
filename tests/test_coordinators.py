from __future__ import annotations

import asyncio
import importlib


def test_tier_config_returns_expected_models():
    from coordinators.tier_config import DEFAULT_TIER, get_tier_config

    assert DEFAULT_TIER == 2
    assert get_tier_config(1) == {
        "base_url": "http://localhost:1234/v1",
        "sensory_model": "qwen2.5-3b-instruct",
        "reason_model": "qwen3.5",
    }
    assert get_tier_config(2)["reason_model"] == "claude-sonnet-4-6"
    assert get_tier_config(3)["reason_model"] == "claude-opus-4-6"


def test_tier_config_falls_back_to_default_for_unknown_tier():
    from coordinators.tier_config import get_tier_config

    assert get_tier_config(999) == get_tier_config(2)


def test_voice_formats_reason_output_as_final_response():
    from coordinators.voice import Voice

    packet = Voice().process({"reason_output": "  Hello, Gopher\n\n"})

    assert packet["final_response"] == "Hello, Gopher."


def test_awareness_runs_pipeline_in_order_without_api_calls():
    from coordinators.awareness import Awareness
    from coordinators.base import Coordinator
    from coordinators.voice import Voice

    class Step(Coordinator):
        def __init__(self, name, key, value):
            self.name = name
            self.key = key
            self.value = value

        def process(self, packet):
            packet.setdefault("order", []).append(self.name)
            packet[self.key] = self.value
            return packet

    awareness = Awareness(
        sensory=Step("sensory", "keywords", ["gopher"]),
        memory=Step("memory", "memory_context", "known context"),
        reason=Step("reason", "reason_output", "  pipeline complete  "),
        voice=Voice(),
    )

    packet = awareness.synchronous_run("What does Gopher remember?")

    assert packet["message"] == "What does Gopher remember?"
    assert packet["input_type"] == "text"
    assert packet["order"] == ["sensory", "memory", "reason"]
    assert packet["final_response"] == "pipeline complete."


def test_awareness_skips_to_voice_when_error_is_present():
    from coordinators.awareness import Awareness
    from coordinators.base import Coordinator
    from coordinators.voice import Voice

    class ErrorStep(Coordinator):
        name = "error"

        def process(self, packet):
            packet["error"] = "classification failed"
            packet["reason_output"] = "  fallback response  "
            return packet

    class ShouldNotRun(Coordinator):
        name = "blocked"

        def process(self, packet):
            raise AssertionError("pipeline should have skipped this coordinator")

    awareness = Awareness(
        sensory=ErrorStep(),
        memory=ShouldNotRun(),
        reason=ShouldNotRun(),
        voice=Voice(),
    )

    packet = awareness.synchronous_run("hello")

    assert packet["error"] == "classification failed"
    assert packet["final_response"] == "fallback response."


def test_awareness_drains_pending_bids_into_reason_context():
    from coordinators.awareness import Awareness
    from coordinators.base import Coordinator
    from coordinators.bid import PRIORITY_PATTERN, Bid
    from coordinators.voice import Voice

    captured = {}

    class SensoryStep(Coordinator):
        name = "sensory"

        def process(self, packet):
            packet["keywords"] = ["gopher"]
            return packet

    class MemoryStep(Coordinator):
        name = "memory"

        def process(self, packet):
            packet["memory_context"] = "Known graph context"
            return packet

    class ReasonStep(Coordinator):
        name = "reason"

        def process(self, packet):
            captured["memory_context"] = packet["memory_context"]
            captured["background_bids"] = packet["background_bids"]
            packet["reason_output"] = "used bid context"
            return packet

    awareness = Awareness(
        sensory=SensoryStep(),
        memory=MemoryStep(),
        reason=ReasonStep(),
        voice=Voice(),
    )
    awareness.bid_queue.submit(
        Bid("pattern_monitor", "A repeated pattern is visible.", PRIORITY_PATTERN, 10.0)
    )

    packet = awareness.synchronous_run("What should I know?")

    assert packet["final_response"] == "used bid context."
    assert "Known graph context" in captured["memory_context"]
    assert "Background coordinator bids:" in captured["memory_context"]
    assert "pattern_monitor" in captured["memory_context"]
    assert captured["background_bids"][0]["content"] == "A repeated pattern is visible."
    assert awareness.bid_queue.qsize() == 0


def test_awareness_gate_bids_respects_active_task_state():
    from coordinators.awareness import Awareness
    from coordinators.bid import PRIORITY_CURIOSITY, Bid

    awareness = Awareness()
    awareness.bid_queue.submit(
        Bid("curiosity", "unresolved question", PRIORITY_CURIOSITY, 20.0)
    )

    awareness.active_task_in_progress = True
    assert asyncio.run(awareness.gate_bids()) == []
    assert awareness.bid_queue.qsize() == 1

    awareness.active_task_in_progress = False
    gated = asyncio.run(awareness.gate_bids())

    assert [bid.content for bid in gated] == ["unresolved question"]
    assert awareness.bid_queue.qsize() == 0


def test_memory_process_uses_retrieved_context_without_connecting_to_graph():
    from coordinators.memory import Memory

    memory = Memory()
    memory.retrieve = lambda keywords, environment="global": "Relevant graph context"

    packet = memory.process({"keywords": ["gopher"]})

    assert packet["memory_context"] == "Relevant graph context"


def test_awareness_assigns_tier_by_complexity_without_overriding_manual_tier():
    from coordinators.awareness import Awareness

    awareness = Awareness()

    simple = {"message": "remember this note", "input_type": "text"}
    awareness.assess_tier(simple)
    assert simple["tier"] == 1

    default = {"message": "What should Gopher-bot remember about this?", "input_type": "text"}
    awareness.assess_tier(default)
    assert default["tier"] == 2

    high_stakes = {"message": "summarize this", "input_type": "text", "high_stakes": True}
    awareness.assess_tier(high_stakes)
    assert high_stakes["tier"] == 3

    manual = {"message": "short", "input_type": "text", "tier": 2}
    awareness.assess_tier(manual)
    assert manual["tier"] == 2


def test_sensory_uses_local_openai_compatible_client_for_tier_one(monkeypatch):
    import coordinators.sensory as sensory_module
    from coordinators.sensory import Sensory

    calls = {}

    class FakeCompletions:
        def create(self, **kwargs):
            calls.update(kwargs)

            class Choice:
                message = type(
                    "Message",
                    (),
                    {"content": '{"intent": "note", "keywords": ["gopher"]}'},
                )()

            return type("Response", (), {"choices": [Choice()]})()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            calls["client_kwargs"] = kwargs
            self.chat = type(
                "Chat",
                (),
                {"completions": FakeCompletions()},
            )()

    monkeypatch.setattr(sensory_module, "OpenAI", FakeOpenAI)

    packet = Sensory().process({"message": "remember this", "input_type": "text", "tier": 1})

    assert packet["intent"] == "note"
    assert packet["keywords"] == ["gopher"]
    assert calls["client_kwargs"] == {
        "base_url": "http://localhost:1234/v1",
        "api_key": "local",
    }
    assert calls["model"] == "qwen2.5-3b-instruct"


def test_sensory_uses_anthropic_client_for_tier_two(monkeypatch):
    import coordinators.sensory as sensory_module
    from coordinators.sensory import Sensory

    calls = {}

    class FakeMessages:
        def create(self, **kwargs):
            calls.update(kwargs)
            block = type(
                "Block",
                (),
                {"text": '{"intent": "question", "keywords": ["memory"]}'},
            )()
            return type("Response", (), {"content": [block]})()

    class FakeAnthropic:
        def __init__(self, **kwargs):
            calls["client_kwargs"] = kwargs
            self.messages = FakeMessages()

    monkeypatch.setattr(sensory_module, "Anthropic", FakeAnthropic)

    packet = Sensory().process({"message": "What do you know?", "input_type": "text", "tier": 2})

    assert packet["intent"] == "question"
    assert packet["keywords"] == ["memory"]
    assert calls["model"] == "claude-3-5-haiku-20241022"


def test_reason_uses_local_openai_compatible_client_for_tier_one(monkeypatch):
    import coordinators.reason as reason_module
    from coordinators.reason import Reason

    calls = {}

    class FakeCompletions:
        def create(self, **kwargs):
            calls.update(kwargs)

            class Choice:
                message = type("Message", (), {"content": "local response"})()

            return type("Response", (), {"choices": [Choice()]})()

    class FakeOpenAI:
        def __init__(self, **kwargs):
            calls["client_kwargs"] = kwargs
            self.chat = type("Chat", (), {"completions": FakeCompletions()})()

    class FakeMemory:
        def store(self, observation):
            calls["stored"] = observation

    monkeypatch.setattr(reason_module, "OpenAI", FakeOpenAI)

    packet = Reason(memory=FakeMemory()).process(
        {
            "message": "remember this",
            "memory_context": "",
            "tier": 1,
        }
    )

    assert packet["reason_output"] == "local response"
    assert calls["client_kwargs"] == {
        "base_url": "http://localhost:1234/v1",
        "api_key": "local",
    }
    assert calls["model"] == "qwen3.5"
    assert "local response" in calls["stored"]


def test_reason_uses_anthropic_client_for_tier_three(monkeypatch):
    import coordinators.reason as reason_module
    from coordinators.reason import Reason

    calls = {}

    class FakeMessages:
        def create(self, **kwargs):
            calls.update(kwargs)
            block = type("Block", (), {"text": "deep response"})()
            return type("Response", (), {"content": [block]})()

    class FakeAnthropic:
        def __init__(self, **kwargs):
            calls["client_kwargs"] = kwargs
            self.messages = FakeMessages()

    class FakeMemory:
        def store(self, observation):
            calls["stored"] = observation

    monkeypatch.setattr(reason_module, "Anthropic", FakeAnthropic)

    packet = Reason(memory=FakeMemory()).process(
        {
            "message": "high stakes",
            "memory_context": "context",
            "tier": 3,
        }
    )

    assert packet["reason_output"] == "deep response"
    assert calls["model"] == "claude-opus-4-6"


def test_bot_respond_uses_awareness_pipeline(monkeypatch):
    bot = importlib.import_module("interface.bot")

    class FakeAwareness:
        def synchronous_run(self, message):
            return {"final_response": f"handled: {message}"}

    monkeypatch.setattr(bot, "awareness", FakeAwareness())

    assert bot.respond("hello") == "handled: hello"
