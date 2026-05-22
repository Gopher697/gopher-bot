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

logger = logging.getLogger(__name__)


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from world_models import config  # noqa: E402


class Reason(Coordinator):
    name = "reason"

    def __init__(self, memory: Memory | None = None):
        self.memory = memory or Memory()

    def process(self, packet: dict) -> dict:
        message = str(packet.get("message", "")).strip()
        memory_context = str(packet.get("memory_context", "")).strip()
        tier = packet.get("tier", DEFAULT_TIER)

        try:
            response = self.generate_response(message, memory_context, tier)
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
    ) -> str:
        tier_config = get_tier_config(tier)
        system_prompt = (
            "You are Gopher-bot's reasoning layer. You have been given "
            "memory context from a knowledge graph. Use it to ground your response.\n"
            f"Memory context: {memory_context}\n"
            "If memory context is empty, say so and respond from first principles.\n"
            "Be direct. Do not perform enthusiasm."
        )
        if tier_config["base_url"]:
            response = _call_local_reasoner(message, system_prompt, tier_config)
        else:
            response = _call_anthropic_reasoner(message, system_prompt, tier_config)
        return _extract_text(response)


def _exchange_observation(message: str, response: str) -> str:
    return f"User said: {message}\nGopher-bot replied: {response}"


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


def _call_local_reasoner(message: str, system_prompt: str, tier_config: dict) -> Any:
    client = OpenAI(base_url=tier_config["base_url"], api_key=config.LM_STUDIO_API_KEY)
    return client.chat.completions.create(
        model=tier_config["reason_model"],
        max_tokens=1024,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ],
    )


def _call_anthropic_reasoner(message: str, system_prompt: str, tier_config: dict) -> Any:
    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return client.messages.create(
        model=tier_config["reason_model"],
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": message}],
    )
