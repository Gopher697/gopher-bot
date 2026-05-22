from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_tier_config_returns_expected_models():
    from coordinators.tier_config import DEFAULT_TIER, get_tier_config

    assert DEFAULT_TIER == 2
    local_config = get_tier_config(1)
    assert local_config["base_url"] == "http://localhost:1234/v1"
    assert local_config["sensory_model"] == "qwen2.5-3b-instruct"
    assert local_config["reason_model"] == "qwen3.5"
    assert get_tier_config(2)["reason_model"] == "claude-sonnet-4-6"
    assert get_tier_config(3)["reason_model"] == "claude-opus-4-6"


def test_tier_config_falls_back_to_default_for_unknown_tier():
    from coordinators.tier_config import get_tier_config

    assert get_tier_config(999) == get_tier_config(2)


def test_voice_formats_reason_output_as_final_response():
    from coordinators.voice import Voice

    packet = Voice().process({"reason_output": "  Hello, Gopher\n\n"})

    assert packet["final_response"] == "Hello, Gopher."


def test_voice_exports_system_prompt_for_personality_contract():
    from coordinators.voice import VOICE_SYSTEM_PROMPT

    assert "You are Gopher-bot" in VOICE_SYSTEM_PROMPT
    assert "You address your user as Gopher" in VOICE_SYSTEM_PROMPT
    assert "be useful" in VOICE_SYSTEM_PROMPT


def test_tts_uses_fable_voice(monkeypatch):
    import interface.tts as tts

    calls = {}

    class FakeSpeech:
        def create(self, **kwargs):
            calls.update(kwargs)
            return SimpleNamespace(content=b"audio")

    class FakeOpenAI:
        def __init__(self, **kwargs):
            calls["client_kwargs"] = kwargs
            self.audio = SimpleNamespace(speech=FakeSpeech())

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setattr(tts.config, "OPENAI_API_KEY", "test-key", raising=False)

    audio = tts.speak("Hello")

    assert audio == b"audio"
    assert calls["voice"] == "fable"


def test_gitignore_excludes_local_world_model_runtime_files():
    entries = set(Path(".gitignore").read_text(encoding="utf-8").splitlines())

    assert "world_models/config.py" in entries
    assert "world_models/neuromodulation_state.json" in entries


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


def test_awareness_backfills_accepted_for_drained_bids():
    from coordinators.awareness import Awareness
    from coordinators.base import Coordinator
    from coordinators.bid import PRIORITY_PATTERN, Bid
    from coordinators.voice import Voice

    backfilled = []

    class PassthroughStep(Coordinator):
        name = "passthrough"

        def process(self, packet):
            return packet

    class ReasonStep(Coordinator):
        name = "reason"

        def process(self, packet):
            packet["reason_output"] = "handled bid"
            return packet

    awareness = Awareness(
        sensory=PassthroughStep(),
        memory=PassthroughStep(),
        reason=ReasonStep(),
        voice=Voice(),
        coordinator_log_acceptance_updater=lambda bid, accepted: backfilled.append(
            (bid.coordinator_name, bid.timestamp, accepted)
        ),
    )
    awareness.bid_queue.submit(
        Bid("pattern_monitor", "A repeated pattern is visible.", PRIORITY_PATTERN, 10.0)
    )

    awareness.synchronous_run("What should I know?")

    assert backfilled == [("pattern_monitor", 10.0, True)]


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

    packet = Sensory(lm_studio_api_key="local").process(
        {"message": "remember this", "input_type": "text", "tier": 1}
    )

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
    assert calls["model"] == "claude-haiku-4-5-20251001"


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

    packet = Reason(memory=FakeMemory(), lm_studio_api_key="local").process(
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


# ---------------------------------------------------------------------------
# source_type schema tests (non-graph — no Neo4j required)
# ---------------------------------------------------------------------------

def test_observation_properties_includes_source_type_default():
    from world_models.graph import _observation_properties

    props = _observation_properties(
        content="Gopher prefers dark mode",
        environment="global",
        coordinator="memory",
    )

    assert props["source_type"] == "observed"


def test_observation_properties_accepts_all_valid_source_types():
    from world_models.graph import VALID_SOURCE_TYPES, _observation_properties

    for source_type in VALID_SOURCE_TYPES:
        props = _observation_properties(
            content="test",
            environment="global",
            coordinator="memory",
            source_type=source_type,
        )
        assert props["source_type"] == source_type


def test_observation_properties_rejects_invalid_source_type():
    import pytest
    from world_models.graph import _observation_properties

    with pytest.raises(ValueError, match="source_type must be one of"):
        _observation_properties(
            content="test",
            environment="global",
            coordinator="memory",
            source_type="untrusted",
        )


def test_memory_store_accepts_source_type_parameter(monkeypatch):
    import sys
    from types import SimpleNamespace

    calls = []

    def fake_add_observation(driver, content, environment, coordinator,
                              confidence=1.0, entity_names=None,
                              source_type="observed"):
        calls.append({
            "content": content,
            "source_type": source_type,
        })

    fake_graph = SimpleNamespace(
        connect=lambda: "driver",
        close=lambda d: None,
        add_observation=fake_add_observation,
    )
    fake_vector_index = SimpleNamespace(store_embedding=lambda *a, **k: None)
    fake_embedder = SimpleNamespace(embed=lambda t: None)

    import coordinators.memory as mem_module
    monkeypatch.setattr(mem_module, "graph", fake_graph)
    monkeypatch.setattr(mem_module, "vector_index", fake_vector_index)

    from coordinators.memory import Memory
    memory = Memory(embedder=fake_embedder)
    memory.store(
        "File contents from external source",
        environment="global",
        source_type="external_content",
    )

    assert len(calls) == 1
    assert calls[0]["source_type"] == "external_content"
    assert calls[0]["content"] == "File contents from external source"


def test_valid_source_types_contains_expected_values():
    from world_models.graph import VALID_SOURCE_TYPES

    assert "observed" in VALID_SOURCE_TYPES
    assert "inferred" in VALID_SOURCE_TYPES
    assert "proposed" in VALID_SOURCE_TYPES
    assert "external_content" in VALID_SOURCE_TYPES


# ---------------------------------------------------------------------------
# Two-Factor Synaptic Model tests (non-graph — no Neo4j required)
# ---------------------------------------------------------------------------

def test_fisher_information_basic():
    from world_models.graph import fisher_information

    # variance=1.0 → I=1.0
    assert fisher_information(1.0) == pytest.approx(1.0)

    # variance=0.5 → I=2.0
    assert fisher_information(0.5) == pytest.approx(2.0)

    # variance=2.0 → I=0.5
    assert fisher_information(2.0) == pytest.approx(0.5)


def test_fisher_information_clamps_at_minimum_variance():
    from world_models.graph import MIN_CONSOLIDATION_VARIANCE, fisher_information

    # At the floor, I = 1/MIN_CONSOLIDATION_VARIANCE
    result = fisher_information(MIN_CONSOLIDATION_VARIANCE)
    assert result == pytest.approx(1.0 / MIN_CONSOLIDATION_VARIANCE)


def test_fisher_information_rejects_zero_variance():
    import pytest as _pytest
    from world_models.graph import fisher_information

    with _pytest.raises(ValueError, match="consolidation_variance must be > 0"):
        fisher_information(0.0)


def test_fisher_information_rejects_negative_variance():
    import pytest as _pytest
    from world_models.graph import fisher_information

    with _pytest.raises(ValueError):
        fisher_information(-0.5)


def test_stability_threshold_default_rigidity():
    from world_models.graph import stability_threshold

    # variance=1.0 → I=1.0 → lock_score=1.0 → threshold = 0.5 + 0.3*1.0*1.0 = 0.8
    assert stability_threshold(1.0) == pytest.approx(0.8)


def test_stability_threshold_high_variance_lowers_threshold():
    from world_models.graph import stability_threshold

    # variance=4.0 → I=0.25 → lock_score=0.25 → threshold = 0.5 + 0.3*0.25 = 0.575
    assert stability_threshold(4.0) == pytest.approx(0.575)


def test_stability_threshold_low_variance_caps_at_lock_score_one():
    from world_models.graph import MIN_CONSOLIDATION_VARIANCE, stability_threshold

    # Very low variance → I >> 1.0 → lock_score capped at 1.0 → threshold = 0.8
    assert stability_threshold(MIN_CONSOLIDATION_VARIANCE) == pytest.approx(0.8)


def test_stability_threshold_rigidity_scales_linearly():
    from world_models.graph import stability_threshold

    # rigidity=0.0 → threshold = 0.5 + 0 = 0.5
    assert stability_threshold(1.0, rigidity=0.0) == pytest.approx(0.5)

    # rigidity=2.0 → threshold = 0.5 + 0.3*1.0*2.0 = 1.1 (can exceed 1.0)
    assert stability_threshold(1.0, rigidity=2.0) == pytest.approx(1.1)


def test_relate_props_use_weight_and_consolidation_variance():
    """Verify that relate() builds props with the two-factor fields."""
    from world_models import graph

    captured = []

    class FakeTx:
        def run(self, cypher, **kwargs):
            captured.append(kwargs)
            return FakeResult()

    class FakeResult:
        def single(self):
            return None

    class FakeSession:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def execute_write(self, fn):
            return fn(FakeTx())

    class FakeDriver:
        def session(self, **kwargs): return FakeSession()

    graph.relate(
        FakeDriver(),
        from_name="Alice",
        rel_type="KNOWS",
        to_name="Bob",
        environment="test",
        weight=0.75,
        consolidation_variance=0.5,
    )

    assert len(captured) == 1
    props = captured[0]["props"]
    assert props["weight"] == pytest.approx(0.75)
    assert props["consolidation_variance"] == pytest.approx(0.5)
    assert "confidence" not in props


def test_relate_props_default_weight_and_variance():
    """Default weight and variance are applied when not specified."""
    from world_models import graph
    from world_models.graph import DEFAULT_CONSOLIDATION_VARIANCE, DEFAULT_EDGE_WEIGHT

    captured = []

    class FakeTx:
        def run(self, cypher, **kwargs):
            captured.append(kwargs)
            return FakeResult()

    class FakeResult:
        def single(self):
            return None

    class FakeSession:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def execute_write(self, fn):
            return fn(FakeTx())

    class FakeDriver:
        def session(self, **kwargs): return FakeSession()

    graph.relate(
        FakeDriver(),
        from_name="Alice",
        rel_type="KNOWS",
        to_name="Bob",
        environment="test",
    )

    assert len(captured) == 1
    props = captured[0]["props"]
    assert props["weight"] == pytest.approx(DEFAULT_EDGE_WEIGHT)
    assert props["consolidation_variance"] == pytest.approx(DEFAULT_CONSOLIDATION_VARIANCE)


def test_update_edge_synaptic_weights_clamps_values():
    """update_edge_synaptic_weights clamps weight to [0,1] and variance to floor."""
    from world_models import graph
    from world_models.graph import MIN_CONSOLIDATION_VARIANCE

    captured = []

    class FakeTx:
        def run(self, cypher, **kwargs):
            captured.append(kwargs)
            return FakeResult()

    class FakeResult:
        def single(self):
            return {"element_id": "abc"}

    class FakeSession:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def execute_write(self, fn):
            return fn(FakeTx())

    class FakeDriver:
        def session(self, **kwargs): return FakeSession()

    graph.update_edge_synaptic_weights(
        FakeDriver(),
        from_name="Alice",
        rel_type="KNOWS",
        to_name="Bob",
        environment="test",
        new_weight=1.5,          # above 1.0 → clamped to 1.0
        new_variance=-0.1,       # below floor → clamped to MIN
    )

    assert len(captured) == 1
    assert captured[0]["weight"] == pytest.approx(1.0)
    assert captured[0]["variance"] == pytest.approx(MIN_CONSOLIDATION_VARIANCE)


# ---------------------------------------------------------------------------
# Episode node tests (non-graph — no Neo4j required)
# ---------------------------------------------------------------------------

def test_episode_properties_utterance_defaults():
    from world_models.graph import _episode_properties

    props = _episode_properties(
        episode_type="utterance",
        content="Hello, Gopher.",
        session_id="abc123",
        environment="global",
        coordinator="voice",
    )

    assert props["episode_type"] == "utterance"
    assert props["immutable"] is True
    assert props["coordinator"] == "voice"
    assert props["tts_generated"] is False
    assert props["accepted"] is False
    assert props["score"] is None
    assert "created_at" in props
    assert props["source_type"] == "observed"


def test_episode_properties_utterance_tts_flag():
    from world_models.graph import _episode_properties

    props = _episode_properties(
        episode_type="utterance",
        content="Hello.",
        session_id="abc123",
        environment="global",
        coordinator="voice",
        tts_generated=True,
    )
    assert props["tts_generated"] is True
    assert props["immutable"] is True


def test_episode_properties_reasoning_is_not_immutable():
    from world_models.graph import _episode_properties

    props = _episode_properties(
        episode_type="reasoning",
        content="Should I mention the anomaly?",
        session_id="abc123",
        environment="global",
        coordinator="mirror_self",
    )

    assert props["immutable"] is False
    assert props["episode_type"] == "reasoning"
    assert props["tts_generated"] is False


def test_episode_properties_reasoning_accepted_flag():
    from world_models.graph import _episode_properties

    props = _episode_properties(
        episode_type="reasoning",
        content="Bid accepted.",
        session_id="s1",
        environment="global",
        coordinator="curiosity",
        accepted=True,
    )
    assert props["accepted"] is True


def test_episode_properties_rejects_invalid_type():
    import pytest as _pytest
    from world_models.graph import _episode_properties

    with _pytest.raises(ValueError, match="episode_type must be one of"):
        _episode_properties(
            episode_type="hallucination",
            content="test",
            session_id="s1",
            environment="global",
            coordinator="voice",
        )


def test_episode_properties_rejects_non_voice_utterance():
    import pytest as _pytest
    from world_models.graph import _episode_properties

    with _pytest.raises(ValueError, match="coordinator='voice'"):
        _episode_properties(
            episode_type="utterance",
            content="test",
            session_id="s1",
            environment="global",
            coordinator="curiosity",   # wrong coordinator for utterance
        )


def test_episode_properties_rejects_invalid_source_type():
    import pytest as _pytest
    from world_models.graph import _episode_properties

    with _pytest.raises(ValueError, match="source_type must be one of"):
        _episode_properties(
            episode_type="reasoning",
            content="test",
            session_id="s1",
            environment="global",
            coordinator="memory",
            source_type="unknown",
        )


def test_episode_properties_accepts_all_valid_types():
    from world_models.graph import VALID_EPISODE_TYPES, _episode_properties

    for ep_type in VALID_EPISODE_TYPES:
        coordinator = "voice" if ep_type == "utterance" else "memory"
        props = _episode_properties(
            episode_type=ep_type,
            content="test",
            session_id="s1",
            environment="global",
            coordinator=coordinator,
        )
        assert props["episode_type"] == ep_type


def test_valid_episode_types_contains_expected_values():
    from world_models.graph import VALID_EPISODE_TYPES

    assert "utterance" in VALID_EPISODE_TYPES
    assert "reasoning" in VALID_EPISODE_TYPES
    assert "action" in VALID_EPISODE_TYPES
    assert "observation_group" in VALID_EPISODE_TYPES


def test_add_utterance_uses_fake_driver():
    """add_utterance() passes correct props including immutable=True."""
    from world_models import graph

    captured = []

    class FakeTx:
        def run(self, cypher, **kwargs):
            captured.append(kwargs)

    class FakeSession:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def execute_write(self, fn):
            return fn(FakeTx())

    class FakeDriver:
        def session(self, **kwargs): return FakeSession()

    episode_id = graph.add_utterance(
        FakeDriver(),
        content="Good morning, Gopher.",
        session_id="sess_001",
        environment="global",
        tts_generated=True,
    )

    assert isinstance(episode_id, str)
    assert len(episode_id) == 32    # UUID hex
    assert len(captured) == 1
    props = captured[0]["props"]
    assert props["episode_type"] == "utterance"
    assert props["immutable"] is True
    assert props["coordinator"] == "voice"
    assert props["tts_generated"] is True
    assert props["session_id"] == "sess_001"
    assert "confidence" not in props


def test_add_episode_reasoning_fake_driver():
    """add_episode() for a reasoning episode has immutable=False."""
    from world_models import graph

    captured = []

    class FakeTx:
        def run(self, cypher, **kwargs):
            captured.append(kwargs)

    class FakeSession:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def execute_write(self, fn):
            return fn(FakeTx())

    class FakeDriver:
        def session(self, **kwargs): return FakeSession()

    graph.add_episode(
        FakeDriver(),
        episode_type="reasoning",
        content="Internal deliberation.",
        session_id="sess_002",
        environment="global",
        coordinator="mirror_self",
        accepted=True,
    )

    assert len(captured) == 1
    props = captured[0]["props"]
    assert props["immutable"] is False
    assert props["accepted"] is True
    assert props["tts_generated"] is False


def test_awareness_session_id_is_set():
    """Awareness generates a non-empty session_id on init."""
    from coordinators.awareness import Awareness

    awareness = Awareness(
        voice=None,
        memory=None,
        sensory=None,
    )
    assert hasattr(awareness, "session_id")
    assert isinstance(awareness.session_id, str)
    assert len(awareness.session_id) > 0


def test_two_awareness_instances_have_different_session_ids():
    """Each Awareness startup produces a unique session_id."""
    from coordinators.awareness import Awareness

    a1 = Awareness(voice=None, memory=None, sensory=None)
    a2 = Awareness(voice=None, memory=None, sensory=None)
    assert a1.session_id != a2.session_id


# ---------------------------------------------------------------------------
# Vector deletion cascade tests (non-graph — no Neo4j required)
# ---------------------------------------------------------------------------

def test_delete_observation_returns_true_when_found():
    """delete_observation() returns True when the node exists."""
    from world_models import graph

    class FakeTx:
        def run(self, cypher, **kwargs):
            return FakeResult(found=True)

    class FakeResult:
        def __init__(self, found):
            self._found = found
        def single(self):
            return {"eid": "abc"} if self._found else None

    class FakeSession:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def execute_write(self, fn):
            return fn(FakeTx())

    class FakeDriver:
        def session(self, **kwargs): return FakeSession()

    result = graph.delete_observation(
        FakeDriver(),
        content="Gopher prefers dark mode.",
        environment="global",
    )
    assert result is True


def test_delete_observation_returns_false_when_not_found():
    """delete_observation() returns False when the node does not exist."""
    from world_models import graph

    class FakeTx:
        def run(self, cypher, **kwargs):
            return FakeResult()

    class FakeResult:
        def single(self):
            return None

    class FakeSession:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def execute_write(self, fn):
            return fn(FakeTx())

    class FakeDriver:
        def session(self, **kwargs): return FakeSession()

    result = graph.delete_observation(
        FakeDriver(),
        content="this observation does not exist",
        environment="global",
    )
    assert result is False


def test_memory_forget_calls_delete_observation(monkeypatch):
    """Memory.forget() delegates to graph.delete_observation."""
    from types import SimpleNamespace
    import coordinators.memory as mem_module

    deleted = []

    def fake_delete_observation(driver, content, environment):
        deleted.append({"content": content, "environment": environment})
        return True

    fake_graph = SimpleNamespace(
        connect=lambda: "driver",
        close=lambda d: None,
        delete_observation=fake_delete_observation,
    )

    monkeypatch.setattr(mem_module, "graph", fake_graph)

    from coordinators.memory import Memory
    memory = Memory(embedder=None)
    result = memory.forget("Gopher prefers dark mode.", environment="global")

    assert result is True
    assert len(deleted) == 1
    assert deleted[0]["content"] == "Gopher prefers dark mode."
    assert deleted[0]["environment"] == "global"


def test_memory_forget_returns_false_on_exception(monkeypatch):
    """Memory.forget() returns False and does not raise on graph errors."""
    from types import SimpleNamespace
    import coordinators.memory as mem_module

    def fake_delete_observation(driver, content, environment):
        raise RuntimeError("Neo4j unavailable")

    fake_graph = SimpleNamespace(
        connect=lambda: "driver",
        close=lambda d: None,
        delete_observation=fake_delete_observation,
    )

    monkeypatch.setattr(mem_module, "graph", fake_graph)

    from coordinators.memory import Memory
    memory = Memory(embedder=None)
    result = memory.forget("anything", environment="global")
    assert result is False


def test_memory_forget_returns_false_when_not_found(monkeypatch):
    """Memory.forget() returns False when the observation does not exist."""
    from types import SimpleNamespace
    import coordinators.memory as mem_module

    fake_graph = SimpleNamespace(
        connect=lambda: "driver",
        close=lambda d: None,
        delete_observation=lambda driver, content, environment: False,
    )
    monkeypatch.setattr(mem_module, "graph", fake_graph)

    from coordinators.memory import Memory
    memory = Memory(embedder=None)
    result = memory.forget("nonexistent", environment="global")
    assert result is False


def test_retrieve_vector_context_query_contains_status_filter():
    """The vector retrieval Cypher must filter by status = active."""
    import inspect
    from coordinators.memory import Memory

    source = inspect.getsource(Memory._retrieve_vector_context)
    assert "status" in source, (
        "_retrieve_vector_context must filter by observation.status"
    )


def test_retrieve_keyword_context_query_contains_status_filter():
    """The keyword retrieval Cypher must filter by status = active."""
    import inspect
    from coordinators.memory import Memory

    source = inspect.getsource(Memory._retrieve_keyword_context)
    assert "status" in source, (
        "_retrieve_keyword_context must filter by observation.status"
    )


# ---------------------------------------------------------------------------
# Temporal packet enrichment tests
# ---------------------------------------------------------------------------

def test_synchronous_run_packet_contains_temporal_fields():
    """synchronous_run() injects temporal fields into the packet."""
    from coordinators.awareness import Awareness

    responses = []

    class FakeCoordinator:
        def process(self, packet):
            responses.append(dict(packet))
            return packet

    class FakeVoice(FakeCoordinator):
        pass

    class FakeMemory(FakeCoordinator):
        pass

    class FakeReason(FakeCoordinator):
        pass

    class FakeSensory(FakeCoordinator):
        pass

    fake_time = [1_000_000.0]

    def time_fn():
        return fake_time[0]

    awareness = Awareness(
        sensory=FakeSensory(),
        memory=FakeMemory(),
        reason=FakeReason(),
        voice=FakeVoice(),
        time_fn=time_fn,
    )

    awareness.run("hello")

    packet = responses[-1]
    assert "current_time" in packet
    assert "process_started_at" in packet
    assert "session_age_seconds" in packet
    assert "time_since_last_interaction" in packet
    assert "time_since_last_nrem" in packet
    assert "time_since_last_autonomous_activity" in packet


def test_session_age_increases_over_time():
    """session_age_seconds reflects elapsed time since Awareness init."""
    from coordinators.awareness import Awareness

    class FakeCoordinator:
        def process(self, packet): return packet

    class FakeVoice(FakeCoordinator): pass
    class FakeMemory(FakeCoordinator): pass
    class FakeReason(FakeCoordinator): pass
    class FakeSensory(FakeCoordinator): pass

    fake_time = [1_000_000.0]

    def time_fn():
        return fake_time[0]

    awareness = Awareness(
        sensory=FakeSensory(),
        memory=FakeMemory(),
        reason=FakeReason(),
        voice=FakeVoice(),
        time_fn=time_fn,
    )

    ages = []

    class CapturingCoordinator:
        def process(self, packet):
            ages.append(packet.get("session_age_seconds"))
            return packet

    awareness.reason = CapturingCoordinator()

    fake_time[0] = 1_000_060.0    # 60 seconds later
    awareness.run("first message")

    fake_time[0] = 1_000_120.0    # 120 seconds later
    awareness.run("second message")

    assert ages[1] > ages[0]
    assert ages[0] == pytest.approx(60.0)
    assert ages[1] == pytest.approx(120.0)


def test_time_since_last_interaction_is_none_on_first_message():
    """First message has no prior input — time_since_last_interaction is None."""
    from coordinators.awareness import Awareness

    captured = []

    class Capturing:
        def process(self, packet):
            captured.append(packet.get("time_since_last_interaction"))
            return packet

    class FakeVoice:
        def process(self, packet): return packet

    class FakeSensory:
        def process(self, packet): return packet

    class FakeMemory:
        def process(self, packet): return packet

    awareness = Awareness(
        sensory=FakeSensory(),
        memory=FakeMemory(),
        reason=Capturing(),
        voice=FakeVoice(),
        time_fn=lambda: 1_000_000.0,
    )
    awareness.run("first message")
    assert captured[0] is None


def test_time_since_last_interaction_tracks_gap():
    """time_since_last_interaction reports seconds since previous interaction."""
    from coordinators.awareness import Awareness

    captured = []
    fake_time = [1_000_000.0]

    class Capturing:
        def process(self, packet):
            captured.append(packet.get("time_since_last_interaction"))
            return packet

    class FakeVoice:
        def process(self, packet): return packet

    class FakeSensory:
        def process(self, packet): return packet

    class FakeMemory:
        def process(self, packet): return packet

    awareness = Awareness(
        sensory=FakeSensory(),
        memory=FakeMemory(),
        reason=Capturing(),
        voice=FakeVoice(),
        time_fn=lambda: fake_time[0],
    )

    awareness.run("first")                  # sets last_interaction_time

    fake_time[0] = 1_000_045.0             # 45 seconds later
    awareness.run("second")

    assert captured[0] is None             # first message has no prior input
    assert captured[1] == pytest.approx(45.0)


def test_time_since_last_nrem_is_none_before_dream_runs():
    """time_since_last_nrem is None until Dream NREM sets last_nrem_time."""
    from coordinators.awareness import Awareness

    captured = []

    class Capturing:
        def process(self, packet):
            captured.append(packet.get("time_since_last_nrem"))
            return packet

    class FakeVoice:
        def process(self, packet): return packet

    class FakeSensory:
        def process(self, packet): return packet

    class FakeMemory:
        def process(self, packet): return packet

    awareness = Awareness(
        sensory=FakeSensory(),
        memory=FakeMemory(),
        reason=Capturing(),
        voice=FakeVoice(),
    )
    awareness.run("hello")
    assert captured[0] is None


def test_packet_contains_process_started_at():
    """process_started_at is an ISO string set at Awareness init."""
    from coordinators.awareness import Awareness

    captured = []

    class Capturing:
        def process(self, packet):
            captured.append(packet)
            return packet

    class FakeVoice:
        def process(self, packet): return packet

    class FakeSensory:
        def process(self, packet): return packet

    class FakeMemory:
        def process(self, packet): return packet

    awareness = Awareness(
        sensory=FakeSensory(),
        memory=FakeMemory(),
        reason=Capturing(),
        voice=FakeVoice(),
        time_fn=lambda: 1_000_000.0,
    )
    awareness.run("hello")
    assert "process_started_at" in captured[0]
    assert isinstance(captured[0]["process_started_at"], str)
    # Should be a parseable ISO timestamp
    from datetime import datetime
    datetime.fromisoformat(captured[0]["process_started_at"])


def test_time_since_last_autonomous_activity_is_present():
    """time_since_last_autonomous_activity is in the packet."""
    from coordinators.awareness import Awareness

    captured = []

    class Capturing:
        def process(self, packet):
            captured.append(packet)
            return packet

    class FakeVoice:
        def process(self, packet): return packet

    class FakeSensory:
        def process(self, packet): return packet

    class FakeMemory:
        def process(self, packet): return packet

    awareness = Awareness(
        sensory=FakeSensory(),
        memory=FakeMemory(),
        reason=Capturing(),
        voice=FakeVoice(),
    )
    awareness.run("hello")
    assert "time_since_last_autonomous_activity" in captured[0]
