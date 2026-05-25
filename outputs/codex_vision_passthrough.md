# Codex Task: Wire image bytes through to the local VLM (Reason)

## Background

When a user attaches an image in Discord, the bridge downloads the raw bytes and
passes them to `Awareness.synchronous_run()` as `image_attachments`. Sensory then
calls `_describe_image()` to generate a text description before Reason runs.

The problem: `_describe_image()` returns `""` when `tier_config["base_url"]` is set
(i.e. any local-LLM tier), because vision was originally only implemented for
Anthropic cloud. The fallback is:

    [filename]: (image attached; no description available at current tier)

That placeholder string becomes `visual_percept.description`, which Reason appends
to the system prompt as plain text. The local VLM (qwen3.5, a vision model loaded
with a multimodal projector) never receives image bytes — only the useless placeholder —
and hallucinates.

## Goal

For **local tiers** (`base_url` is set): skip the pre-description step entirely.
Instead, pass the raw image bytes through the packet to Reason, which sends them as
`image_url` content blocks in the multimodal OpenAI-compatible API call. qwen3.5
will actually see the image.

For **cloud tiers** (`base_url` is None): keep the existing `_describe_image()` /
Anthropic vision flow unchanged.

## Changes required

### 1. `coordinators/sensory.py`

In `Sensory.process()`, replace the entire image-attachment block (lines 43–70,
the one that calls `_describe_image()` and sets `visual_percept`) with the
following logic:

```python
image_attachments = packet.pop("image_attachments", None) or []
if image_attachments and "visual_percept" not in packet:
    tier_config = get_tier_config(packet.get("tier", DEFAULT_TIER))
    if tier_config.get("base_url"):
        # Local VLM tier: pass raw bytes to Reason; skip pre-description.
        # The VLM will receive the actual image data as multimodal content.
        raw_images: list[dict] = []
        for attachment in image_attachments:
            filename = attachment.get("filename", "image")
            data = attachment.get("data", b"")
            if not data:
                continue
            media_type = _media_type_from_filename(filename)
            encoded = base64.standard_b64encode(data).decode("utf-8")
            raw_images.append({
                "filename": filename,
                "media_type": media_type,
                "data_b64": encoded,
            })
        if raw_images:
            packet["raw_images_for_reason"] = raw_images
            # Record the percept event so Awareness knows an image was attached,
            # but leave description empty so Memory does not ingest a placeholder.
            import time as _time_mod
            packet["visual_percept"] = {
                "timestamp": _time_mod.time(),
                "objects": [],
                "motion_detected": False,
                "motion_region": None,
                "scene_type": "user_attachment",
                "text_in_scene": [],
                "faces_detected": 0,
                "pose_summary": "",
                "description": "",
            }
    else:
        # Cloud tier: generate a text description via the Anthropic vision API.
        descriptions: list[str] = []
        for attachment in image_attachments:
            filename = attachment.get("filename", "image")
            data = attachment.get("data", b"")
            if not data:
                continue
            desc = _describe_image(data, filename, tier_config)
            if desc:
                descriptions.append(f"[{filename}]: {desc}")
            else:
                descriptions.append(
                    f"[{filename}]: (image attached; no description available)"
                )
        if descriptions:
            combined_description = "\n".join(descriptions)
            import time as _time_mod
            packet["visual_percept"] = {
                "timestamp": _time_mod.time(),
                "objects": [],
                "motion_detected": False,
                "motion_region": None,
                "scene_type": "user_attachment",
                "text_in_scene": [],
                "faces_detected": 0,
                "pose_summary": "",
                "description": combined_description,
            }
```

No other changes to `sensory.py`. The `_describe_image()` function and all cloud
paths stay exactly as they are.

---

### 2. `coordinators/reason.py`

#### 2a. `Reason.process()` — extract raw images before calling `generate_response`

Add one line after the visual_percept extraction (after `_vp = packet.get(...)`) to
pop the raw images from the packet:

```python
raw_images: list[dict] = packet.pop("raw_images_for_reason", None) or []
```

Then pass `raw_images` to `generate_response()`:

```python
response = self.generate_response(
    message,
    memory_context,
    tier,
    visual_description,
    raw_images=raw_images,
)
```

#### 2b. `Reason.generate_response()` — accept and forward raw images

Add `raw_images: list[dict] | None = None` as a keyword parameter.

When `raw_images` is non-empty AND `tier_config["base_url"]` is set, do NOT append
any "Visual context" text to `system_prompt` (the model will see the image directly).
When `raw_images` is empty and `visual_description` is non-empty, append the existing
visual context text as before.

Pass `raw_images` through to `_call_local_reasoner()`.

Full updated signature and body:

```python
def generate_response(
    self,
    message: str,
    memory_context: str,
    tier: int = DEFAULT_TIER,
    visual_description: str = "",
    raw_images: list[dict] | None = None,
) -> str:
    tier_config = get_tier_config(tier)
    system_prompt = (
        f"You are {BOT_NAME}'s reasoning layer. You have been given "
        "memory context from a knowledge graph. Use it to ground your response.\n"
        f"Memory context: {memory_context}\n"
        "If memory context is empty, say so and respond from first principles.\n"
        "Be direct. Do not perform enthusiasm."
    )
    # Only add text-based visual context when NOT passing raw image bytes.
    # When raw_images is present the VLM sees the image directly.
    if visual_description and not raw_images:
        system_prompt += (
            "\n\nVisual context (image attached by user): "
            f"{visual_description}"
        )
    if tier_config["base_url"]:
        response = _call_local_reasoner(
            message,
            system_prompt,
            tier_config,
            lm_studio_api_key=self.lm_studio_api_key,
            raw_images=raw_images or [],
        )
    else:
        response = _call_anthropic_reasoner(message, system_prompt, tier_config)
    return _extract_text(response)
```

#### 2c. `_call_local_reasoner()` — build multimodal content when images are present

Add `raw_images: list[dict] | None = None` parameter.

When `raw_images` is non-empty, build a list of content blocks for the user message:
each image as an `image_url` block (inline base64 data URI), then the text message.
When `raw_images` is empty, keep the existing plain-string user message.

```python
def _call_local_reasoner(
    message: str,
    system_prompt: str,
    tier_config: dict,
    lm_studio_api_key: str | None = None,
    raw_images: list[dict] | None = None,
) -> Any:
    api_key = (
        lm_studio_api_key
        if lm_studio_api_key is not None
        else config.LM_STUDIO_API_KEY
    )
    client = OpenAI(
        base_url=tier_config["base_url"],
        api_key=api_key,
        timeout=REASON_TIMEOUT_SECONDS,
    )
    if raw_images:
        user_content: list[dict] = []
        for img in raw_images:
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{img['media_type']};base64,{img['data_b64']}"
                },
            })
        if message:
            user_content.append({"type": "text", "text": message})
    else:
        user_content = message  # type: ignore[assignment]

    return client.chat.completions.create(
        model=tier_config["reason_model"],
        max_tokens=1024,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )
```

---

### 3. `tests/test_vision_passthrough.py` — new test file

Create `tests/test_vision_passthrough.py`. The tests must NOT require Neo4j, LM Studio,
or Anthropic to be running. Use `unittest.mock.patch` throughout.

Cover:

**Sensory — local tier image handling**

```
test_sensory_local_tier_sets_raw_images:
    Build a packet with tier=TIER_LOCAL and pass a fake image_attachments list
    ({"filename": "test.png", "data": b"\x89PNG..."}).
    Patch get_tier_config to return {"base_url": "http://localhost:1234/v1", ...}.
    Call Sensory().process(packet).
    Assert packet["raw_images_for_reason"] is a non-empty list.
    Assert packet["raw_images_for_reason"][0]["media_type"] == "image/png".
    Assert packet["raw_images_for_reason"][0]["data_b64"] is a non-empty string.
    Assert packet.get("visual_percept", {}).get("description") == "".
    Assert "image_attachments" not in packet.
```

```
test_sensory_cloud_tier_uses_describe_image:
    Patch get_tier_config to return {"base_url": None, "sensory_model": "claude-haiku-4-5-20251001"}.
    Patch _describe_image to return "A palm tree pixel art image.".
    Build packet with fake image_attachments.
    Call Sensory().process(packet).
    Assert "raw_images_for_reason" not in packet.
    Assert "[test.png]: A palm tree pixel art image." in packet["visual_percept"]["description"].
```

```
test_sensory_local_tier_no_images_no_key:
    Build a packet with tier=TIER_LOCAL and no image_attachments.
    Call Sensory().process(packet).
    Assert "raw_images_for_reason" not in packet.
```

**Reason — multimodal call construction**

```
test_call_local_reasoner_with_images_builds_multimodal_content:
    Call _call_local_reasoner directly with a raw_images list containing one item
    (media_type="image/png", data_b64="abc123").
    Patch openai.OpenAI so the client.chat.completions.create call is captured.
    Assert the user message passed to create() is a list (not a string).
    Assert the list contains one dict with type="image_url".
    Assert the image_url["url"] starts with "data:image/png;base64,".
    Assert the list contains one dict with type="text" whose text equals the message.
```

```
test_call_local_reasoner_without_images_sends_string:
    Call _call_local_reasoner with raw_images=None or raw_images=[].
    Assert the user message passed to create() is a plain string.
```

```
test_generate_response_no_visual_text_when_raw_images_present:
    Patch _call_local_reasoner to capture the system_prompt argument.
    Call Reason().generate_response(..., visual_description="some text", raw_images=[{...}]).
    Assert "Visual context" not in the captured system_prompt.
```

```
test_generate_response_visual_text_when_no_raw_images:
    Patch _call_local_reasoner to capture the system_prompt argument.
    Call Reason().generate_response(..., visual_description="A palm tree.", raw_images=[]).
    Assert "Visual context" in the captured system_prompt.
```

---

## What NOT to change

- `interface/discord_bot.py` — it already downloads image bytes correctly.
- `coordinators/awareness.py` — `packet_overrides` already flows `image_attachments` through.
- Cloud image description logic (`_describe_image`, `_call_anthropic_reasoner`) — leave untouched.
- `coordinators/memory.py` — Memory already skips ingestion when `visual_percept.description` is empty.
- `world_models/config.py` — no config changes needed; the existing `base_url` / model fields drive everything.

## Acceptance criteria

```
pytest tests/test_vision_passthrough.py -v   # all tests pass
pytest --basetemp .tmp/pytest-tmp -q          # full suite still passes
```

After implementing, run the bot, send a Discord message with an image attached, and
confirm the LM Studio developer log shows a request body containing
`"type": "image_url"` rather than the placeholder string.

## Security reminder

Do not stage or commit `world_models/config.py`. Run `git status` before committing.
