from __future__ import annotations

from coordinators.reason import Reason


class _MemorySink:
    def store(self, _observation: str) -> None:
        return None


def test_reason_passes_visual_description_to_generate_response():
    """visual_percept.description is extracted from packet and passed to generate_response."""
    reason = Reason(memory=_MemorySink())
    packet = {
        "message": "what do you see?",
        "memory_context": "",
        "tier": 1,
        "visual_percept": {
            "description": "A wet floor sign in a hallway.",
            "scene_type": "user_attachment",
            "objects": [],
            "motion_detected": False,
            "motion_region": None,
            "text_in_scene": [],
            "faces_detected": 0,
            "pose_summary": "",
            "timestamp": 0.0,
        },
    }
    called_with = {}

    def fake_generate(message, memory_context, tier, visual_description="", raw_images=None):
        called_with["visual_description"] = visual_description
        return "I see a wet floor sign."

    reason.generate_response = fake_generate
    reason.process(packet)
    assert called_with["visual_description"] == "A wet floor sign in a hallway."


def test_reason_visual_description_empty_when_no_percept():
    """When visual_percept is absent, visual_description defaults to empty string."""
    reason = Reason(memory=_MemorySink())
    packet = {"message": "hello", "memory_context": "", "tier": 1}
    called_with = {}

    def fake_generate(message, memory_context, tier, visual_description="", raw_images=None):
        called_with["visual_description"] = visual_description
        return "hi"

    reason.generate_response = fake_generate
    reason.process(packet)
    assert called_with["visual_description"] == ""


def test_generate_response_includes_visual_description_in_system_prompt():
    """When visual_description is non-empty, it appears in the system prompt sent to LLM."""
    reason = Reason()
    captured = {}

    def fake_local(message, system_prompt, tier_config, lm_studio_api_key=None, raw_images=None):
        captured["system_prompt"] = system_prompt
        mock = type("R", (), {"choices": [
            type("C", (), {"message": type("M", (), {"content": "ok"})()})()
        ]})()
        return mock

    import coordinators.reason as reason_mod
    original = reason_mod._call_local_reasoner
    reason_mod._call_local_reasoner = fake_local
    try:
        from coordinators.tier_config import TIER_LOCAL
        reason.generate_response("look", "", TIER_LOCAL, "A hallway with a mop.")
    finally:
        reason_mod._call_local_reasoner = original

    assert "A hallway with a mop." in captured["system_prompt"]
    assert "Visual context" in captured["system_prompt"]


def test_generate_response_no_visual_section_when_empty():
    """When visual_description is empty, system prompt has no Visual context section."""
    reason = Reason()
    captured = {}

    def fake_local(message, system_prompt, tier_config, lm_studio_api_key=None, raw_images=None):
        captured["system_prompt"] = system_prompt
        mock = type("R", (), {"choices": [
            type("C", (), {"message": type("M", (), {"content": "ok"})()})()
        ]})()
        return mock

    import coordinators.reason as reason_mod
    original = reason_mod._call_local_reasoner
    reason_mod._call_local_reasoner = fake_local
    try:
        from coordinators.tier_config import TIER_LOCAL
        reason.generate_response("hi", "", TIER_LOCAL, "")
    finally:
        reason_mod._call_local_reasoner = original

    assert "Visual context" not in captured["system_prompt"]
