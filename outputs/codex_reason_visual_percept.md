# Codex Task — Wire visual_percept into Reason context

## Context

`coordinators/sensory.py` puts image attachment descriptions into the packet as
`packet["visual_percept"]["description"]` — either a real LLM-generated description
(TIER_STANDARD via Haiku) or a fallback note at TIER_LOCAL. That percept rides
through the coordinator pipeline all the way to Reason, where it is silently ignored.

`Reason.process()` reads only `message` and `memory_context`. The LLM never sees
that an image was attached, so the bot always responds as if no image was sent.

**Only `coordinators/reason.py` changes.** No other files.

---

## Security invariant

Run `git status` before committing. If `world_models/config.py` appears, STOP.

---

## Change — `coordinators/reason.py`

### In `Reason.process()`

After reading `memory_context`, add one line to extract the visual description:

```python
def process(self, packet: dict) -> dict:
    message = str(packet.get("message", "")).strip()
    memory_context = str(packet.get("memory_context", "")).strip()
    visual_description = str(
        (packet.get("visual_percept") or {}).get("description") or ""
    ).strip()
    tier = packet.get("tier", DEFAULT_TIER)

    try:
        response = self.generate_response(message, memory_context, tier, visual_description)
    except Exception as e:
        logger.exception("Reason.generate_response failed: %s", e)
        packet["error"] = "response generation failed"
        return packet

    packet["reason_output"] = response
    self.memory.store(_exchange_observation(message, response))
    return packet
```

### In `Reason.generate_response()`

Add `visual_description: str = ""` as a parameter and append it to the system prompt
when non-empty:

```python
def generate_response(
    self,
    message: str,
    memory_context: str,
    tier: int = DEFAULT_TIER,
    visual_description: str = "",
) -> str:
    tier_config = get_tier_config(tier)
    system_prompt = (
        f"You are {BOT_NAME}'s reasoning layer. You have been given "
        "memory context from a knowledge graph. Use it to ground your response.\n"
        f"Memory context: {memory_context}\n"
        "If memory context is empty, say so and respond from first principles.\n"
        "Be direct. Do not perform enthusiasm."
    )
    if visual_description:
        system_prompt += f"\n\nVisual context (image attached by user): {visual_description}"
    if tier_config["base_url"]:
        response = _call_local_reasoner(
            message,
            system_prompt,
            tier_config,
            lm_studio_api_key=self.lm_studio_api_key,
        )
    else:
        response = _call_anthropic_reasoner(message, system_prompt, tier_config)
    return _extract_text(response)
```

---

## Tests — add to `tests/test_reason.py`

Add the following tests. Do not modify any existing test assertions.

```python
def test_reason_passes_visual_description_to_generate_response():
    """visual_percept.description is extracted from packet and passed to generate_response."""
    reason = Reason()
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

    def fake_generate(message, memory_context, tier, visual_description=""):
        called_with["visual_description"] = visual_description
        return "I see a wet floor sign."

    reason.generate_response = fake_generate
    reason.process(packet)
    assert called_with["visual_description"] == "A wet floor sign in a hallway."


def test_reason_visual_description_empty_when_no_percept():
    """When visual_percept is absent, visual_description defaults to empty string."""
    reason = Reason()
    packet = {"message": "hello", "memory_context": "", "tier": 1}
    called_with = {}

    def fake_generate(message, memory_context, tier, visual_description=""):
        called_with["visual_description"] = visual_description
        return "hi"

    reason.generate_response = fake_generate
    reason.process(packet)
    assert called_with["visual_description"] == ""


def test_generate_response_includes_visual_description_in_system_prompt():
    """When visual_description is non-empty, it appears in the system prompt sent to LLM."""
    reason = Reason()
    captured = {}

    def fake_local(message, system_prompt, tier_config, lm_studio_api_key=None):
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

    def fake_local(message, system_prompt, tier_config, lm_studio_api_key=None):
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
```

---

## Verification

```
pytest tests/test_reason.py -v
pytest --ignore=tests/test_graph.py --basetemp .tmp/pytest_reason_percept -v
```

Confirm `world_models/config.py` is not staged:
```
git status
```

Commit:
```
git commit -m "feat: wire visual_percept.description into Reason system prompt"
```
