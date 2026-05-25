from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from anthropic import Anthropic
from openai import OpenAI

from coordinators.base import Coordinator
from coordinators.memory import Memory
from coordinators.tier_config import DEFAULT_TIER, get_tier_config
from world_models.config_utils import BOT_NAME

logger = logging.getLogger(__name__)


REASON_TIMEOUT_SECONDS = 90

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from world_models import config  # noqa: E402


class Reason(Coordinator):
    name = "reason"

    def __init__(
        self,
        memory: Memory | None = None,
        lm_studio_api_key: str | None = None,
    ):
        self.memory = memory or Memory()
        self.lm_studio_api_key = lm_studio_api_key

    def process(self, packet: dict) -> dict:
        message = str(packet.get("message", "")).strip()
        memory_context = str(packet.get("memory_context", "")).strip()
        _vp = packet.get("visual_percept") or {}
        raw_images: list[dict] = packet.pop("raw_images_for_reason", None) or []
        visual_description = str(_vp.get("description") or "").strip()

        # For live desktop percepts, append a compact element index so Reason
        # can refer to on-screen labels when composing Hands actions.
        if _vp.get("scene_type") == "desktop" and visual_description:
            _text_items = _vp.get("text_in_scene") or []
            _obj_items = _vp.get("objects") or []
            _text_labels = [
                t.get("text", "") for t in _text_items[:12]
                if isinstance(t, dict) and t.get("text")
            ]
            _obj_labels = [
                o.get("label", "") for o in _obj_items[:6]
                if isinstance(o, dict) and o.get("label") and o.get("label") not in _text_labels
            ]
            all_labels = _text_labels + _obj_labels
            if all_labels:
                label_list = ", ".join(f'"{lbl}"' for lbl in all_labels[:18])
                visual_description += f"\nVisible elements: {label_list}"
        tier = packet.get("tier", DEFAULT_TIER)

        try:
            response = self.generate_response(
                message,
                memory_context,
                tier,
                visual_description,
                raw_images=raw_images,
            )
        except Exception as e:
            logger.exception("Reason.generate_response failed: %s", e)
            packet["error"] = "response generation failed"
            return packet

        packet["reason_output"] = response
        self.memory.store(_exchange_observation(message, response))
        return packet

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
        # Only add text-based visual context when not passing raw image bytes.
        # When raw_images is present, the VLM sees the image directly.
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


def _exchange_observation(message: str, response: str) -> str:
    return f"User said: {message}\n{BOT_NAME} replied: {response}"


def _extract_text(response: Any) -> str:
    choices = getattr(response, "choices", None)
    if choices:
        content = getattr(getattr(choices[0], "message", None), "content", None)
        if content is None and isinstance(choices[0], dict):
            content = choices[0].get("message", {}).get("content")
        if content:
            return str(content).strip()

    parts = []
    for block in getattr(response, "content", []) or []:
        text = getattr(block, "text", None)
        if text is None and isinstance(block, dict):
            text = block.get("text")
        if text:
            parts.append(str(text))
    return "\n".join(parts).strip()


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
        user_content: list[dict] | str = []
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
        user_content = message

    return client.chat.completions.create(
        model=tier_config["reason_model"],
        max_tokens=1024,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )


def _call_anthropic_reasoner(message: str, system_prompt: str, tier_config: dict) -> Any:
    client = Anthropic(
        api_key=config.ANTHROPIC_API_KEY,
        timeout=REASON_TIMEOUT_SECONDS,
    )
    return client.messages.create(
        model=tier_config["reason_model"],
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": message}],
    )
